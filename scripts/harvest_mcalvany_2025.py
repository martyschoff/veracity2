"""Harvest David McAlvany predictions for 2025 from mcalvany.com weekly commentary.

Site pattern: /weekly-commentary/<slug>/ episode pages with transcripts.
"""
import json
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_lock import locked_data

BASE = Path(r'C:/Users/schof/veracity2')
STATE = BASE / 'data' / 'harvest_mcal_state.json'

EXTRACT_PROMPT = """Extract AT MOST 2 predictions from this transcript. Rules:
- Own voice only: David McAlvany (host). Never extract from quoted material - guest statements (this is an interview show; guests like analysts or fund managers speak often), "X believes/says/thinks" third-person reports, press-release quotes: skip all of those.
- Only genuine predictions with a testable future outcome (price levels, dates, timeframes, percentages). Prescriptions, facts, and vague views: skip.
- The prediction date is the episode date: {date}.

TRANSCRIPT:
{transcript}

Answer STRICTLY as JSON: {{"predictions": [{{"claim": "...", "excerpt": "1-3 supporting sentences"}}]}}"""


def fetch(url, timeout=60):
    r = subprocess.run(['curl', '-s', '-L', '-m', str(timeout), url],
                       capture_output=True, text=True, timeout=timeout + 10)
    return r.stdout or ''


def episode_list():
    """Collect 2025 episode URLs + dates from the archive pages."""
    eps = {}
    for page in ['https://mcalvany.com/commentary/episodes',
                 'https://mcalvany.com/commentary/episodes/page/2/',
                 'https://mcalvany.com/commentary/episodes/page/3/',
                 'https://mcalvany.com/commentary/episodes/page/4/']:
        html = fetch(page)
        for m in re.finditer(r'href="(https://mcalvany\.com/weekly-commentary/[a-z0-9-]+/)"[^>]*>.{0,400}?(\w{3} \d{1,2},? 2025)', html, re.S):
            url, date = m.group(1), m.group(2)
            try:
                from datetime import datetime
                iso = datetime.strptime(date, '%b %d, 2025' if ', ' in date else '%b %d 2025').date().isoformat()
                eps[url] = iso
            except Exception:
                pass
    return eps


def episode_text(url):
    html = fetch(url)
    text = re.sub(r'<script.*?</script>|<style.*?</style>', ' ', html, flags=re.S)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    m = re.search(r'Kevin:\s*Welcome to the McAlvany Weekly Commentary(.{0,20000})', text, re.I)
    return ('Kevin: Welcome to the McAlvany Weekly Commentary' + m.group(1)) if m else text[:12000]


def main():
    st = json.load(open(STATE, encoding='utf-8')) if STATE.exists() else {'done': {}, 'stats': []}
    eps = episode_list()
    print(f'{len(eps)} episodes of 2025 found', flush=True)
    for i, (url, date) in enumerate(sorted(eps.items(), key=lambda kv: kv[1])):
        if url in st['done']:
            continue
        t = episode_text(url)
        res = None
        n_added = 0
        if len(t) > 800:
            from hermes_tools import web_extract
            res = json.loads(json.dumps({})) if False else None
            # extraction via ollama on nimo
            import subprocess as sp
            body = json.dumps({'model': 'qwen3:32b', 'stream': False, 'think': False,
                               'messages': [{'role': 'user', 'content': EXTRACT_PROMPT.format(date=date, transcript=t[:15000])}],
                               'options': {'num_predict': 600, 'temperature': 0.2}})
            r = sp.run(['curl', '-s', '-m', '300', 'http://100.84.167.88:11434/api/chat', '-d', body],
                       capture_output=True, text=True, timeout=310)
            try:
                res = json.loads(re.search(r'\{.*\}', json.loads(r.stdout)['message']['content'], re.S).group(0))
            except Exception:
                res = None
        if res and res.get('predictions'):
            with locked_data() as fresh:
                for pred in res['predictions'][:2]:
                    claim = (pred.get('claim') or '').strip()
                    if len(claim) < 20:
                        continue
                    fresh['predictions'].append({
                        'id': f"pred_{int(time.time()*1000)%10**10}_{url[-12:]}",
                        'individual_name': 'David McAlvany',
                        'date': date,
                        'category': 'finance',
                        'claim': claim,
                        'source_url': url,
                        'transcript_excerpt': (pred.get('excerpt') or claim)[:400],
                        'verdict': None,
                        'created_at': date,
                    })
                    n_added += 1
        st['done'][url] = n_added
        st['stats'].append({'url': url, 'date': date, 'added': n_added})
        print(f"{i+1}/{len(eps)} {date} +{n_added}", flush=True)
        STATE.write_text(json.dumps(st, indent=1), encoding='utf-8')
    total = sum(v for v in st['done'].values() if isinstance(v, int))
    print(f'HARVEST_MCAL_DONE: {total} predictions from {len(eps)} episodes', flush=True)


if __name__ == '__main__':
    main()
