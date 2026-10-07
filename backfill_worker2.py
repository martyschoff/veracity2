# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Backfill worker v2: reads work_queue.json, fetches transcripts via
hermes_tools.web_extract (RPC), extracts predictions via LLM, stages to
staged_predictions.jsonl, checkpoints (merge -> render -> deploy) every
25 predictions or every 30 minutes. Resumable via done-url set."""
import json, os, re, subprocess, sys, time, hashlib, urllib.request

os.chdir('C:/Users/schof/veracity2')
sys.path.insert(0, os.path.abspath('.'))
from hermes_tools import web_extract

PRIMARY = 'http://upthread64.tail5b3b50.ts.net:11434/v1/chat/completions'
PRIMARY_MODEL = 'qwen3-coder:30b-32k'
FALLBACK = 'http://127.0.0.1:18434/v1/chat/completions'
FALLBACK_MODEL = 'Qwen3.8-27B-UD-Q4_K_M'
FALLBACK_KEY = 'OyISwmqwQMak4mEOtO3zajuzSY8clG73'
CHECK_EVERY = 25
CHECK_SECS = 1800

CHANNEL_ORDER = ['ZeihanonGeopolitics', 'GZEROMedia', 'PeterHDiamandis']
NAME = {'ZeihanonGeopolitics': 'Peter Zeihan', 'GZEROMedia': 'Ian Bremmer',
        'PeterHDiamandis': 'Peter Diamandis'}
CATS = {'Peter Zeihan': ['geopolitics', 'energy', 'china', 'ukraine', 'finance'],
        'Ian Bremmer': ['geopolitics'],
        'Peter Diamandis': ['ai']}
BREMMER_FILTER = ['quick take', 'ian explain', 'ask ian']


def chat(url, model, key, prompt, timeout=280):
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    body = {'model': model, 'messages': [{'role': 'user', 'content': prompt}],
            'stream': False, 'max_tokens': 2000}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    r = json.load(urllib.request.urlopen(req, timeout=timeout))
    m = r['choices'][0]['message']
    txt = (m.get('content') or m.get('reasoning_content') or '')
    return txt


def llm(transcript, title, date, categories):
    prompt = f"""You extract falsifiable predictions from video transcripts. Upload date: {date}. Title: {title}
Allowed categories: {', '.join(categories)}.

Transcript (may be truncated):
{transcript[:12000]}

Extract at most 2 predictions stated by the SPEAKER in their own voice about the FUTURE relative to {date} (specific dates, quantities, prices, percentages, timeframes, or election/geopolitical outcomes are best). EXCLUDE anything said by interviewers, quoted people, or attributed to third parties. EXCLUDE any claim referencing a year/time already passed as of {date}, and exclude vague opinions with no measurable outcome. If nothing qualifies return [].

Return ONLY a JSON array like:
[{{"claim":"...","category":"{categories[0]}","measurement_type":"quantitative","quote":"exact supporting sentence from transcript"}}]
measurement_type is "quantitative" or "subjective". Max 2 items."""
    txt = None
    try:
        txt = chat(PRIMARY, PRIMARY_MODEL, None, prompt)
    except Exception as e:
        log(f'PRIMARY_LLM_FAIL {e}; trying fallback')
    if not txt or not re.search(r'\[', txt):
        try:
            txt = chat(FALLBACK, FALLBACK_MODEL, FALLBACK_KEY, prompt)
        except Exception as e:
            log(f'FALLBACK_LLM_FAIL {e}')
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


def log(msg):
    line = f"{time.strftime('%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open('backfill_progress.md', 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def checkpoint():
    try:
        r = subprocess.run(['python', 'merge_and_deploy.py'], capture_output=True,
                           text=True, timeout=280)
        log('CHECKPOINT rc=%s %s' % (r.returncode, (r.stdout or r.stderr)[-300:]))
    except Exception as e:
        log('CHECKPOINT_FAIL %s' % e)


def main():
    done_urls = {p['source_url'] for p in json.load(open('data/predictions.json'))['predictions']}
    if os.path.exists('staged_predictions.jsonl'):
        for l in open('staged_predictions.jsonl', encoding='utf-8'):
            try:
                done_urls.add(json.loads(l)['source_url'])
            except Exception:
                pass
    q = json.load(open('work_queue.json'))
    since_ckpt = 0
    last_ckpt = time.time()
    processed = 0
    for chan in CHANNEL_ORDER:
        person = NAME[chan]
        videos = q.get(chan, [])
        if chan == 'GZEROMedia':
            videos = [v for v in videos if any(k in v['title'].lower() for k in BREMMER_FILTER)]
        log(f'== {chan} ({person}): {len(videos)} videos ==')
        for v in videos:
            url = f'https://www.youtube.com/watch?v={v["id"]}'
            if url in done_urls:
                continue
            attempts = 0
            c = ''
            while attempts < 2 and '## Transcript' not in c:
                attempts += 1
                try:
                    res = web_extract(urls=[url], char_limit=25000)
                    c = (res.get('results') or [{}])[0].get('content', '') or ''
                except Exception as e:
                    log(f'FETCH_FAIL {v["id"]}: {e} RAW={json.dumps(res)[:200] if isinstance(res, dict) else "?"}')
                    c = ''
                    time.sleep(3)
            if '## Transcript' not in c:
                log(f'NO_TRANSCRIPT {v["id"]} {v["date"]} :: {v["title"][:60]}')
                done_urls.add(url)
                continue
            mdate = re.search(r'Uploaded at\*\*: (\d{4}-\d{2}-\d{2})', c)
            real = mdate.group(1) if mdate else v['date']
            transcript = c[c.find('## Transcript') + len('## Transcript'):]
            if real < '2024-04-30':
                log(f'OUT_OF_RANGE {v["id"]} {real}')
                done_urls.add(url)
                continue
            try:
                items = llm(transcript, v['title'], real, CATS[person])
            except Exception as e:
                log(f'LLM_FAIL {v["id"]}: {e}')
                time.sleep(5)
                continue
            n = 0
            with open('staged_predictions.jsonl', 'a', encoding='utf-8') as f:
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
            done_urls.add(url)
            processed += 1
            since_ckpt += n
            log(f'OK {v["id"]} {real} preds={n} :: {v["title"][:70]}')
            if since_ckpt >= CHECK_EVERY or time.time() - last_ckpt >= CHECK_SECS:
                checkpoint()
                since_ckpt = 0
                last_ckpt = time.time()
    checkpoint()
    log(f'ALL DONE processed={processed}')


if __name__ == '__main__':
    main()
