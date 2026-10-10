# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Sequential harvest daemon: polls data/harvest_queue.json for source configs,
runs each source harvester (fetch -> extract on nimo qwen3:32b -> gate on nimble),
writes results into predictions.json via locked_data.

Sources each declare a type: youtube | mcalvany_site | article_archive
Model split: extraction=qwen3:32b (judgment), gate=nimble:latest (speed).
"""
import datetime
import json
import re
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(r'C:/Users/schof/veracity2')
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / 'scripts'))
from data_lock import locked_data

QUEUE = BASE / 'data' / 'harvest_queue.json'
LOG = BASE / 'data' / 'harvest_daemon.log'
HEARTBEAT = BASE / 'data' / 'harvest_heartbeat.txt'

NIMO = 'http://100.84.167.88:11500'
GATE_HOST = 'http://100.73.201.124:11500'  # mlsfs - nimble resident, no model-swap war with the 32b extractor
EXTRACT_MODEL = 'qwen3:32b'
GATE_MODEL = 'nimble:latest'


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as fh:
        fh.write(line + '\n')


def heartbeat():
    HEARTBEAT.write_text(time.strftime('%Y-%m-%d %H:%M:%S'), encoding='utf-8')


def call_nimo(model, prompt, max_tokens=2000, timeout=280):
    import urllib.request
    body = json.dumps({'model': model, 'stream': False, 'think': False,
                       'messages': [{'role': 'user', 'content': prompt}],
                       'options': {'num_predict': max_tokens, 'temperature': 0.2}}).encode()
    req = urllib.request.Request(f'{NIMO}/api/chat', data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read()).get('message', {}).get('content', '')


def parse_predictions(raw):
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(m.group(0)).get('predictions', [])
    except json.JSONDecodeError:
        return []


def fetch_text(url):
    """Fetch a page/article/transcript as plain text."""
    import urllib.request as _ur
    req = _ur.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    html = ''
    try:
        html = _ur.urlopen(req, timeout=90).read().decode('utf-8', errors='replace')
    except Exception:
        pass
    if len(html) < 2500:
        # bot-walled or JS-rendered: fall back to r.jina.ai reader
        try:
            html = _ur.urlopen(_ur.Request(f'https://r.jina.ai/{url}', headers={'User-Agent': 'Mozilla/5.0'}), timeout=120).read().decode('utf-8', errors='replace')
        except Exception:
            html = html or ''
    if not html:
        return ''
    text = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def youtube_transcripts(channel_url, since, out_dir, page_size=15):
    """yt-dlp transcripts for a channel since date, PAGED: fetch newest `page_size`
    un-downloaded videos per call (bounded time, honest heartbeats, incremental processing).
    Returns list of (url, date, text) for newly fetched srts only."""
    out_dir.mkdir(parents=True, exist_ok=True)
    import sys as _sys
    yt = [ _sys.executable, '-m', 'yt_dlp']  # module form: immune to PATH stripping
    # page through newest videos: playlist-items N:M window, advancing until we hit already-downloaded ones
    start = 1
    new_srts = []
    while start <= 400:  # hard page cap per cycle
        r = subprocess.run([*yt, '--skip-download', '--write-auto-subs', '--sub-langs', 'en',
                            '--convert-subs', 'srt', '--dateafter', since,
                            '--playlist-items', f'{start}:{start + page_size - 1}',
                            '--no-overwrites',
                            '-o', str(out_dir / '%(id)s_%(upload_date)s.%(ext)s'),
                            channel_url + '/videos'], capture_output=True, text=True, timeout=900)
        before = {p.name for p in out_dir.glob('*.srt')}
        # nothing new -> we've reached already-harvested territory; stop paging
        after = {p.name for p in out_dir.glob('*.srt')}
        fresh = after - before
        if not fresh:
            break
        new_srts.extend(fresh)
        start += page_size
        if len(new_srts) >= 30:  # batch cap: process these before fetching more
            break
    results = []
    for srt in sorted(out_dir.glob('*.srt')):
        m = re.match(r'(.+)_(\d{8})', srt.name)
        if not m:
            continue
        vid, ymd = m.group(1), m.group(2)
        date = f'{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}'
        lines = [l for l in srt.read_text(encoding='utf-8', errors='replace').splitlines()
                 if l.strip() and not l.strip().isdigit() and '-->' not in l]
        text = ' '.join(lines)
        if len(text) > 800:
            results.append((f'https://www.youtube.com/watch?v={vid}', date, text[:20000]))
    return results


def extract_predictions(text, person, date, url):
    prompt = (
        "Extract AT MOST 2 predictions from this transcript. ONLY own-voice predictions by "
        f"{person}. Never extract from quoted material, guest statements (this is an interview "
        "show), or 'X believes/says' third-person reports. Prescriptions and vague views: skip. "
        "Only testable future outcomes with numbers, dates, or timeframes. The prediction date "
        f"is {date}. Answer STRICTLY JSON: "
        '{"predictions": [{"claim": "...", "excerpt": "..."}]}\n\nTRANSCRIPT:\n' + text[:15000]
    )
    raw = call_nimo(EXTRACT_MODEL, prompt)
    preds = parse_predictions(raw)
    out = []
    for pred in preds[:2]:
        claim = (pred.get('claim') or '').strip()
        if len(claim) < 20:
            continue
        out.append({'claim': claim, 'excerpt': (pred.get('excerpt') or claim)[:400]})
    return out


def gate_call(model, prompt, max_tokens=300, timeout=280):
    """Call the gate host (mlsfs) - same API shape as call_nimo."""
    import urllib.request
    body = json.dumps({'model': model, 'stream': False, 'think': False,
                       'messages': [{'role': 'user', 'content': prompt}],
                       'options': {'num_predict': max_tokens, 'temperature': 0.2}}).encode()
    req = urllib.request.Request(f'{GATE_HOST}/api/chat', data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read()).get('message', {}).get('content', '')


def gate_prediction(claim):
    """nimble gate (on mlsfs): is this a genuine dated testable prediction? Returns 'prediction'|'reject'."""
    prompt = (
        "Classify this statement: is it a genuine, dated, testable PREDICTION about future events, "
        "or is it EDUCATION/explanation, a PRESCRIPTION (advice), a QUOTED third-party view, or "
        "VAGUE commentary? Answer ONLY one word: prediction or reject.\n\nSTATEMENT: " + claim
    )
    raw = gate_call(GATE_MODEL, prompt, max_tokens=300)
    return 'prediction' if 'prediction' in (raw or '').lower() else 'reject'


def add_prediction(person, category, claim, date, url, excerpt):
    with locked_data() as data:
        # dedupe: same person + same claim prefix
        for existing in data['predictions']:
            if existing.get('individual_name') == person and existing.get('claim', '')[:80] == claim[:80]:
                return False
        import time as _t
        data['predictions'].append({
            'id': f'pred_{int(_t.time())}_{hash(claim) % 10**8:08d}',
            'individual_name': person,
            'date': date,
            'category': category,
            'claim': claim,
            'source_url': url,
            'transcript_excerpt': excerpt,
            'verdict': None,
            'judgements': [],
        })
        return True


def process_source(src):
    """Process one queued source. Returns (processed, added)."""
    name = src['person']
    st_key = f"harvest_{src['id']}_state.json"
    state_file = BASE / 'data' / st_key
    state = json.load(open(state_file, encoding='utf-8')) if state_file.exists() else {'done': {}, 'stats': []}

    log(f"harvesting {name} ({src['type']}) since {src.get('since', 'n/a')}")
    pieces = []
    if src['type'] == 'youtube':
        pieces = youtube_transcripts(src['url'], src.get('since', '20250101'), BASE / 'data' / f'harvest_tmp_{src["id"]}')
    elif src['type'] == 'mcalvany_site':
        # episode index -> fetch RAW (jina keeps markdown links with slugs)
        import urllib.request as _ur
        idx_html = _ur.urlopen(_ur.Request(f'https://r.jina.ai/{src["url"]}', headers={'User-Agent': 'Mozilla/5.0'}), timeout=120).read().decode('utf-8', errors='replace')
        slugs = set(re.findall(r'mcalvany\.com/weekly-commentary/([a-z0-9-]+)/', idx_html))
        log(f'  found {len(slugs)} episode slugs')
        for slug in sorted(slugs):
            url = f'https://mcalvany.com/weekly-commentary/{slug}/'
            if url in state['done']:
                continue
            text = fetch_text(url)
            dm = re.search(r'Posted on (\w+ \d{1,2}, \d{4})', text)
            date = src.get('fallback_date', '2026-01-01')
            if dm:
                from datetime import datetime as _dt
                try:
                    date = _dt.strptime(dm.group(1), '%B %d, %Y').date().isoformat()
                except ValueError:
                    pass
            if len(text) > 1500:
                pieces.append((url, date, text[:20000]))
    elif src['type'] == 'article_archive':
        # index page(s) -> follow article links -> fetch each article
        import urllib.request as _ur
        max_articles = src.get('max_articles', 15)
        seen = set(state['done'].keys())
        article_urls = []
        for idx_url in src['urls']:
            try:
                html = _ur.urlopen(_ur.Request(f'https://r.jina.ai/{idx_url}', headers={'User-Agent': 'Mozilla/5.0'}), timeout=120).read().decode('utf-8', errors='replace')
            except Exception:
                continue
            # collect links matching the domain, excluding the index itself
            dom = re.escape(idx_url.split('/')[2])
            links = re.findall(r'https?://' + dom + r'/[^\s")\]]+', html)
            for l in links:
                l = l.rstrip('.,;')
                if l not in seen and l != idx_url and l not in article_urls:
                    article_urls.append(l)
        pat = src.get('article_pattern')
        if pat:
            article_urls = [l for l in article_urls if re.search(pat, l)]
        article_urls = article_urls[:max_articles]
        log(f'  following {len(article_urls)} article links')
        for url in article_urls:
            if url in state['done']:
                continue
            text = fetch_text(url)
            if len(text) > 2500:
                pieces.append((url, src.get('date', datetime.date.today().isoformat()), text[:20000]))

    processed = added = 0
    for url, date, text in pieces:
        if url in state['done']:
            continue
        preds = extract_predictions(text, name, date, url)
        kept = []
        for pr in preds:
            if gate_prediction(pr['claim']) == 'prediction':
                if add_prediction(name, src.get('category', 'finance'), pr['claim'], date, url, pr['excerpt']):
                    kept.append(pr['claim'][:60])
                    added += 1
        state['done'][url] = len(kept)
        state['stats'].append({'url': url, 'date': date, 'added': len(kept)})
        processed += 1
        state_file.write_text(json.dumps(state, indent=1), encoding='utf-8')
        log(f'  {url[:70]} -> {len(kept)} kept')
    log(f'  {name}: processed {processed}, added {added}')
    # remaining = did this cycle fetch new material that may continue next cycle?
    remaining = src['type'] == 'youtube' and processed > 0
    return processed, added, remaining


def main():
    log('harvest daemon started (extract qwen3:32b on nimo / gate nimble on mlsfs)')
    while True:
        heartbeat()
        try:
            if not QUEUE.exists():
                time.sleep(120)
                continue
            queue = json.load(open(QUEUE, encoding='utf-8'))
            pending = [s for s in queue.get('sources', []) if not s.get('completed')]
            if not pending:
                time.sleep(300)
                continue
            src = pending[0]
            _, _, more = process_source(src)
            if not more:
                src['completed'] = True
                log(f"source {src['person']} complete")
            QUEUE.write_text(json.dumps(queue, indent=1), encoding='utf-8')
        except BaseException as e:
            import traceback
            log(f'error {type(e).__name__}: {e}')
            log(traceback.format_exc()[-500:])
            time.sleep(120)


if __name__ == '__main__':
    main()
