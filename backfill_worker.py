"""Backfill worker: fetches transcripts via hermes_tools.web_extract, extracts
predictions via local LLM, stages to staged_predictions.jsonl, checkpoints
every CHECK_EVERY videos (merge -> render -> deploy). Resumable."""
import json, os, re, subprocess, sys, time, hashlib, urllib.request

os.chdir('C:/Users/schof/veracity2')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hermes_tools import web_extract

LLM_URL='http://upthread64.tail5b3b50.ts.net:11434/v1/chat/completions'
CHECK_EVERY=25
START=time.time()

CHANNELS={
 'Peter Zeihan':   {'file':'videos_ZeihanonGeopolitics.txt','lo':'20240430','hi':'20260812'},
 'Ian Bremmer':    {'file':'videos_GZEROMedia.txt','lo':'20240430','hi':'20260918',
                    'title_filter':['quick take','ian explain','ask ian']},
 'Peter Diamandis':{'file':'videos_PD2.txt','lo':'20240430','hi':'20241108'},
}
BOUNDARIES={'videos_ZeihanonGeopolitics.txt':None,'videos_GZEROMedia.txt':None,'videos_PD2.txt':413}

def real_date(vid):
    r=subprocess.run(['python','-m','yt_dlp','--skip-download','--no-warnings',
        '--print','%(upload_date)s', f'https://www.youtube.com/watch?v={vid}'],
        capture_output=True,text=True,timeout=120)
    for tok in r.stdout.split():
        if len(tok)==8 and tok.isdigit(): return tok
    return None

def build_gap_queue():
    """Return per-channel list of {id,date,title} in gap window, oldest first."""
    q={}
    bfile='boundaries.json'
    bounds=json.load(open(bfile)) if os.path.exists(bfile) else {}
    for name,cfg in CHANNELS.items():
        vids=[]
        for line in open(cfg['file'],encoding='utf-8'):
            p=line.rstrip('\n').split('|',2)
            if len(p)<3 or len(p[0])!=11: continue
            vids.append({'id':p[0],'approx':p[1],'title':p[2]})
        key=cfg['file']
        if key not in bounds:
            lo,hi=0,len(vids)-1; boundary=len(vids)
            while lo<=hi:
                mid=(lo+hi)//2
                d=real_date(vids[mid]['id'])
                print('BS',name,mid,d,flush=True)
                if d is None: lo=mid+1; continue
                if d<cfg['lo']: boundary=mid; hi=mid-1
                else: lo=mid+1
            bounds[key]=boundary
            json.dump(bounds,open(bfile,'w'))
        # walk down (older) from boundary-1 while date >= lo
        gap=[]
        i=bounds[key]-1
        while i>=0:
            d=vids[i].get('real') or real_date(vids[i]['id'])
            vids[i]['real']=d
            if d is None: i-=1; continue
            if d<cfg['lo']: break
            if d>=cfg['hi']: i-=1; continue  # above covered range... actually newer; skip
            if 'title_filter' in cfg and not any(k in vids[i]['title'].lower() for k in cfg['title_filter']):
                i-=1; continue
            gap.append({'id':vids[i]['id'],'date':f'{d[:4]}-{d[4:6]}-{d[6:]}','title':vids[i]['title']})
            i-=1
        gap.reverse()  # oldest first
        q[name]=gap
        print(name,'gap videos:',len(gap),gap[0] if gap else None,gap[-1] if gap else None,flush=True)
    json.dump(q,open('gap_queue.json','w'))
    return q

def llm(transcript, title, date, categories):
    prompt=f"""You extract falsifiable predictions from video transcripts. Upload date: {date}. Title: {title}
Allowed categories: {', '.join(categories)}.

Transcript (may be truncated):
{transcript[:12000]}

Extract at most 2 predictions stated by the speaker about the FUTURE relative to {date} (specific dates, quantities, prices, percentages, timeframes, or election/geopolitical outcomes are best). EXCLUDE any claim referencing a year/time already passed as of {date}, and exclude vague opinions with no measurable outcome. If nothing qualifies return [].

Return ONLY a JSON array like:
[{{"claim":"...","category":"geopolitics","measurement_type":"quantitative","quote":"exact supporting sentence from transcript"}}]
measurement_type is "quantitative" or "subjective". Max 2 items."""
    req=urllib.request.Request(LLM_URL,
        data=json.dumps({'model':'qwen3-coder:30b-32k',
            'messages':[{'role':'user','content':prompt}],'stream':False,'options':{'num_ctx':16384}}).encode(),
        headers={'Content-Type':'application/json'})
    r=json.load(urllib.request.urlopen(req,timeout=300))
    txt=r['choices'][0]['message']['content']
    txt=re.sub(r'<think>.*?</think>','',txt,flags=re.S)
    m=re.search(r'\[.*\]',txt,flags=re.S)
    if not m: return []
    try: items=json.loads(m.group(0))
    except Exception:
        try: items=json.loads(m.group(0).replace("'",'"'))
        except Exception: return []
    return items[:2] if isinstance(items,list) else []

def log(msg):
    line=f"{time.strftime('%H:%M:%S')} {msg}"
    print(line,flush=True)
    with open('backfill_progress.md','a',encoding='utf-8') as f: f.write(line+'\n')

def checkpoint():
    r=subprocess.run(['python','merge_and_deploy.py'],capture_output=True,text=True,timeout=280)
    log('CHECKPOINT rc=%s %s'%(r.returncode, (r.stdout or r.stderr)[-300:]))

def main():
    done_urls={p['source_url'] for p in json.load(open('data/predictions.json'))['predictions']}
    if os.path.exists('staged_predictions.jsonl'):
        for l in open('staged_predictions.jsonl',encoding='utf-8'):
            try: done_urls.add(json.loads(l)['source_url'])
            except Exception: pass
    q=json.load(open('gap_queue.json')) if os.path.exists('gap_queue.json') else build_gap_queue()
    cats={'Peter Zeihan':['geopolitics','energy','china','ukraine','finance'],
          'Ian Bremmer':['geopolitics'],
          'Peter Diamandis':['ai']}
    since_ckpt=0
    for name,videos in q.items():
        log(f'== {name}: {len(videos)} gap videos ==')
        for v in videos:
            url=f'https://www.youtube.com/watch?v={v["id"]}'
            if url in done_urls: continue
            try:
                res=web_extract(urls=[url],char_limit=20000)
                c=res['results'][0].get('content','')
            except Exception as e:
                log(f'FETCH_FAIL {v["id"]}: {e}'); continue
            mdate=re.search(r'Uploaded at\*\*: (\d{4}-\d{2}-\d{2})',c)
            real=mdate.group(1) if mdate else v['date']
            i=c.find('## Transcript')
            if i<0:
                log(f'NO_TRANSCRIPT {v["id"]} {real}'); continue
            transcript=c[i+len('## Transcript'):]
            # drop stale-dated videos outside window
            if real<'2024-04-30':
                log(f'OUT_OF_RANGE(pre) {v["id"]} {real}'); done_urls.add(url); continue
            try:
                items=llm(transcript,v['title'],real,cats[name])
            except Exception as e:
                log(f'LLM_FAIL {v["id"]}: {e}'); time.sleep(5); continue
            n=0
            with open('staged_predictions.jsonl','a',encoding='utf-8') as f:
                for it in items:
                    claim=(it.get('claim') or '').strip()
                    quote=(it.get('quote') or '').strip()
                    if not claim or not quote: continue
                    rec={'id':'pred_%s_%s'%(time.strftime('%Y%m%d%H%M%S'),hashlib.md5((url+claim).encode()).hexdigest()[:12]),
                         'individual_name':name,'date':real,
                         'category':it.get('category') if it.get('category') in cats[name] else cats[name][0],
                         'claim':claim,'source_url':url,'transcript_excerpt':quote[:400],
                         'verdict':None,'created_at':time.strftime('%Y-%m-%dT%H:%M:%S'),
                         'measurement_type':it.get('measurement_type') if it.get('measurement_type') in ('quantitative','subjective') else 'subjective'}
                    f.write(json.dumps(rec,ensure_ascii=False)+'\n')
                    n+=1
            done_urls.add(url); since_ckpt+=n
            log(f'OK {v["id"]} {real} preds={n} :: {v["title"][:70]}')
            if since_ckpt>=CHECK_EVERY:
                checkpoint(); since_ckpt=0
    checkpoint()
    log('ALL DONE')

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='build':
        build_gap_queue()
    else:
        if not os.path.exists('gap_queue.json'): build_gap_queue()
        main()
