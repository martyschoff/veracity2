"""Resumable batch runner, executed inside the Hermes kernel (web_extract only
works there). Each invocation processes videos until TIME_BUDGET seconds elapse,
appending to staged_predictions.jsonl and updating state.json."""
import json, os, re, sys, time, hashlib, urllib.request

os.chdir('C:/Users/schof/veracity2')
sys.path.insert(0, os.path.abspath('.'))
from hermes_tools import web_extract

PRIMARY = 'http://upthread64.tail5b3b50.ts.net:11434/v1/chat/completions'
PRIMARY_MODEL = 'qwen3-coder:30b-32k'
FALLBACK = 'http://127.0.0.1:18434/v1/chat/completions'
FALLBACK_MODEL = 'Qwen3.8-27B-UD-Q4_K_M'
FALLBACK_KEY = 'OyISwmqwQMak4mEOtO3zajuzSY8clG73'
CHECK_SECS = 1800
TIME_BUDGET = 215
STATE_FILE = 'state.json'
STAGED = 'staged_predictions.jsonl'

CHANNEL_ORDER = ['ZeihanonGeopolitics', 'GZEROMedia', 'PeterHDiamandis']
NAME = {'ZeihanonGeopolitics': 'Peter Zeihan', 'GZEROMedia': 'Ian Bremmer',
        'PeterHDiamandis': 'Peter Diamandis'}
CATS = {'Peter Zeihan': ['geopolitics', 'energy', 'china', 'ukraine', 'finance'],
        'Ian Bremmer': ['geopolitics'],
        'Peter Diamandis': ['ai']}
BREMMER_FILTER = ['quick take', 'ian explain', 'ask ian']


def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    q = json.load(open('work_queue.json'))
    chans = {}
    for chan in CHANNEL_ORDER:
        vids = q.get(chan, [])
        if chan == 'GZEROMedia':
            vids = [v for v in vids if any(k in v['title'].lower() for k in BREMMER_FILTER)]
        chans[chan] = vids
    done = {p['source_url'] for p in json.load(open('data/predictions.json'))['predictions']}
    if os.path.exists(STAGED):
        for l in open(STAGED, encoding='utf-8'):
            try:
                done.add(json.loads(l)['source_url'])
            except Exception:
                pass
    return {'chans': chans, 'ci': 0, 'vi': 0, 'done': sorted(done),
            'last_ckpt': time.time(), 'stats': {}}


def save_state(st):
    st['done'] = sorted(st['done'])
    json.dump(st, open(STATE_FILE, 'w'))


def log(msg):
    line = f"{time.strftime('%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open('backfill_progress.md', 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def llm(transcript, title, date, categories):
    prompt = f"""You extract falsifiable predictions from video transcripts. Upload date: {date}. Title: {title}
Allowed categories: {', '.join(categories)}.

Transcript (may be truncated):
{transcript[:12000]}

Extract at most 2 predictions stated by the SPEAKER in their own voice about the FUTURE relative to {date} (specific dates, quantities, prices, percentages, timeframes, or election/geopolitical outcomes are best). EXCLUDE anything said by interviewers, quoted people, or attributed to third parties. EXCLUDE any claim referencing a year/time already passed as of {date}, and exclude vague opinions with no measurable outcome. If nothing qualifies return [].

Return ONLY a JSON array like:
[{{"claim":"...","category":"{categories[0]}","measurement_type":"quantitative","quote":"exact supporting sentence from transcript"}}]
measurement_type is "quantitative" or "subjective". Max 2 items."""
    body = {'model': PRIMARY_MODEL, 'messages': [{'role': 'user', 'content': prompt}],
            'stream': False, 'max_tokens': 2000}
    try:
        req = urllib.request.Request(PRIMARY, data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json'})
        r = json.load(urllib.request.urlopen(req, timeout=240))
        m = r['choices'][0]['message']
        txt = (m.get('content') or m.get('reasoning_content') or '')
        if not re.search(r'\[', txt):
            raise ValueError('no array')
    except Exception as e:
        log(f'PRIMARY_LLM_FAIL {e}')
        body2 = {'model': FALLBACK_MODEL, 'messages': [{'role': 'user', 'content': prompt}],
                 'stream': False, 'max_tokens': 2000}
        try:
            req = urllib.request.Request(FALLBACK, data=json.dumps(body2).encode(),
                                         headers={'Content-Type': 'application/json',
                                                  'Authorization': 'Bearer ' + FALLBACK_KEY})
            r = json.load(urllib.request.urlopen(req, timeout=240))
            m = r['choices'][0]['message']
            txt = (m.get('content') or m.get('reasoning_content') or '')
        except Exception as e2:
            log(f'FALLBACK_LLM_FAIL {e2}')
            return []
    txt = re.sub(r'<think>.*?</think>', '', txt, flags=re.S)
    m = re.search(r'\[.*\]', txt, flags=re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except Exception:
        try:
            items = json.loads(m.group(0).replace("'", '"'))
        except Exception:
            return []
    return items[:2] if isinstance(items, list) else []


def checkpoint():
    try:
        import subprocess
        r = subprocess.run(['python', 'merge_and_deploy.py'], capture_output=True,
                           text=True, timeout=280)
        log('CHECKPOINT rc=%s merged/out: %s' % (r.returncode, (r.stdout or r.stderr)[-200:]))
        st['last_ckpt'] = time.time()
    except Exception as e:
        log('CHECKPOINT_FAIL %s' % e)


def run():
    global st
    st = load_state()
    st['done'] = set(st['done'])
    t0 = time.time()
    ok = no_tr = fail = preds = 0
    while time.time() - t0 < TIME_BUDGET:
        chans = st['chans']
        ci = st['ci']
        if ci >= len(CHANNEL_ORDER):
            break
        chan = CHANNEL_ORDER[ci]
        vids = chans.get(chan, [])
        vi = st['vi']
        if vi >= len(vids):
            log(f'== {chan} COMPLETE ==')
            st['ci'] = ci = ci + 1
            st['vi'] = 0
            continue
        person = NAME[chan]
        batch, metas = [], []
        j = vi
        while j < len(vids) and len(batch) < 6:
            url = f'https://www.youtube.com/watch?v={vids[j]["id"]}'
            if url not in st['done']:
                batch.append(url)
                metas.append((j, vids[j], url))
            j += 1
        st['vi'] = j
        if not batch:
            continue
        try:
            res = web_extract(urls=batch, char_limit=25000)
            pages = {r.get('url', '').split('&')[0]: r for r in res.get('results', [])}
        except Exception as e:
            log(f'BATCH_FETCH_FAIL {e}')
            time.sleep(10)
            continue
        for j, v, url in metas:
            if time.time() - t0 > TIME_BUDGET - 30:
                st['vi'] = j  # revisit this video next call
                break
            page = pages.get(url) or pages.get(f'https://www.youtube.com/watch?v={v["id"]}') or {}
            c = page.get('content', '') or ''
            if '## Transcript' not in c:
                log(f'NO_TRANSCRIPT {chan} {v["id"]} {v["date"]} :: {v["title"][:60]}')
                no_tr += 1
                st['done'].add(url)
                st['vi'] = j + 1
                continue
            mdate = re.search(r'Uploaded at\*\*: (\d{4}-\d{2}-\d{2})', c)
            real = mdate.group(1) if mdate else v['date']
            transcript = c[c.find('## Transcript') + len('## Transcript'):]
            if real < '2024-04-30':
                log(f'OUT_OF_RANGE {v["id"]} {real}')
                st['done'].add(url)
                st['vi'] = j + 1
                continue
            items = llm(transcript, v['title'], real, CATS[person])
            st['done'].add(url)
            st['vi'] = j + 1
            n = 0
            with open(STAGED, 'a', encoding='utf-8') as f:
                for it in items:
                    claim = (it.get('claim') or '').strip()
                    quote = (it.get('quote') or '').strip()
                    if not claim or not quote:
                        continue
                    rec = {'id': 'pred_%s_%s' % (time.strftime('%Y%m%d%H%M%S'),
                                                 hashlib.md5((url + claim).encode()).hexdigest()[:12]),
                           'individual_name': person, 'date': real,
                           'category': it.get('category') if it.get('category') in CATS[person] else CATS[person][0],
                           'claim': claim, 'source_url': url, 'transcript_excerpt': quote[:400],
                           'verdict': None, 'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
                           'measurement_type': it.get('measurement_type') if it.get('measurement_type') in ('quantitative', 'subjective') else 'subjective'}
                    f.write(json.dumps(rec, ensure_ascii=False) + '\n')
                    n += 1
            ok += 1
            preds += n
            log(f'OK {chan} {v["id"]} {real} preds={n} :: {v["title"][:60]}')
        st['stats'][chan] = st['stats'].get(chan, 0) + len(metas)
        if time.time() - st['last_ckpt'] >= CHECK_SECS:
            checkpoint()
    save_state(st)
    total_vids = sum(len(st['chans'].get(c, [])) for c in CHANNEL_ORDER)
    print(f'PROGRESS done_urls={len(st["done"])} of ~{total_vids} ok={ok} no_tr={no_tr} preds={preds} '
          f'pos=ch{st["ci"]}:{st["vi"]} elapsed={time.time()-t0:.0f}s', flush=True)
    if st['ci'] >= len(CHANNEL_ORDER):
        checkpoint()
        log('ALL_CHANNELS_DONE')
        return 'DONE'
    return 'CONTINUE'


if __name__ == '__main__':
    print(run())
