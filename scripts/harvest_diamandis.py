# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Harvest Peter Diamandis predictions for 2025-2026.

Pattern: dated channel listing in one pass (yt-dlp) -> transcripts -> LLM extraction
(max 2 per source, own voice only) -> append to predictions.json via data_lock.
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
YTDLP = r'C:/Users/schof/AppData/Local/hermes/tools/python-3.14.7+20260901-win32-x64/Scripts/yt-dlp.exe'
TMP = Path(r'C:/Users/schof/AppData/Local/hermes/cache/scratch')
STATE = BASE / 'data' / 'harvest_dia_state.json'
CHANNEL = 'https://www.youtube.com/@peterdiamandis/videos'
SINCE = '20250101'

EXTRACT_PROMPT = """Extract AT MOST 2 predictions from this transcript. Rules:
- Own voice only: the speaker is Peter Diamandis (host). Never extract from quoted material (guest statements, "X believes/says" third-person reports).
- Only genuine predictions: forecasts with a testable future outcome. Prescriptions ("we should"), facts, roadmap/marketing talk, vague aspirations: skip.
- Prioritize measurable claims: dates, dollar amounts, percentages, timeframes.
- The prediction date is the video upload date: {upload_date}.

TRANSCRIPT:
{transcript}

Answer STRICTLY as JSON: {{"predictions": [{{"claim": "...", "excerpt": "the 1-3 sentences supporting it"}}]}}"""


def ollama_json(prompt, model='qwen3:32b', host='100.84.167.88:11434', timeout=300):
    body = json.dumps({'model': model, 'stream': False, 'think': False,
                       'messages': [{'role': 'user', 'content': prompt}],
                       'options': {'num_predict': 600, 'temperature': 0.2}})
    r = subprocess.run(['curl', '-s', '-m', str(timeout), f'http://{host}/api/chat', '-d', body],
                       capture_output=True, text=True, timeout=timeout + 10)
    try:
        c = json.loads(r.stdout)['message']['content']
        m = re.search(r'\{.*\}', c, re.S)
        return json.loads(m.group(0))
    except Exception:
        return None


def list_videos():
    r = subprocess.run(
        [YTDLP, '--extractor-args', 'youtube:player_client=android_vr', '--flat-playlist',
         '--print', '%(id)s|%(upload_date)s|%(title).80s', '--dateafter', SINCE, CHANNEL],
        capture_output=True, text=True, timeout=300)
    out = []
    for line in r.stdout.splitlines():
        parts = line.split('|', 2)
        if len(parts) == 3 and re.match(r'^[\w-]{11}$', parts[0]):
            out.append({'id': parts[0], 'date': parts[1], 'title': parts[2]})
    return out


def transcript_text(vid):
    r = subprocess.run([YTDLP, '--extractor-args', 'youtube:player_client=android_vr',
                        '--skip-download', '--write-auto-subs', '--sub-langs', 'en',
                        '--sub-format', 'vtt', '-o', str(TMP / f'hdia_{vid}'),
                        f'https://www.youtube.com/watch?v={vid}'],
                       capture_output=True, text=True, timeout=180)
    found = list(TMP.glob(f'hdia_{vid}*.vtt'))
    if not found:
        return None
    vtt = found[0].read_text(encoding='utf-8', errors='replace')
    text = re.sub(r'<[^>]+>', ' ', vtt)
    text = re.sub(r'\d+:\d+:\d+\.\d+ --> \d+:\d+:\d+\.\d+', ' ', text)
    text = re.sub(r'align:start position:\d+%', ' ', text)
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith(('WEBVTT', 'Kind:', 'Language:')) and not re.match(r'^\d+$', l.strip())]
    out, prev = [], None
    for l in lines:
        if l != prev:
            out.append(l)
        prev = l
    t = ' '.join(out)
    # dedupe the auto-sub rolling repeats: keep first occurrence of phrases
    return re.sub(r'(\b\w+.*?\b)(?=.*\1)', '', t) if len(t) > 20000 else t


def main():
    st = json.load(open(STATE, encoding='utf-8')) if STATE.exists() else {'done': {}, 'stats': []}
    vids = list_videos()
    print(f'{len(vids)} videos since {SINCE}', flush=True)
    for i, v in enumerate(vids):
        if v['id'] in st['done']:
            continue
        # dedupe: skip if any prediction already sourced from this video
        t = transcript_text(v['id'])
        if not t or len(t) < 300:
            st['done'][v['id']] = 'no-transcript'
        else:
            res = ollama_json(EXTRACT_PROMPT.format(upload_date=v['date'], transcript=t[:15000]))
            n_added = 0
            if res and res.get('predictions'):
                with locked_data() as fresh:
                    byid = {q['id'] for q in fresh['predictions']}
                    # find Diamandis id name
                    for pred in res['predictions'][:2]:
                        claim = (pred.get('claim') or '').strip()
                        if not claim or len(claim) < 20:
                            continue
                        new_id = f"pred_{int(time.time()*1000)%10**10}_{v['id'][:8]}"
                        if new_id in byid:
                            continue
                        fresh['predictions'].append({
                            'id': new_id,
                            'individual_name': 'Peter Diamandis',
                            'date': v['date'],
                            'category': 'ai',
                            'claim': claim,
                            'source_url': f'https://www.youtube.com/watch?v={v["id"]}',
                            'transcript_excerpt': (pred.get('excerpt') or claim)[:400],
                            'verdict': None,
                            'created_at': v['date'],
                        })
                        n_added += 1
            st['done'][v['id']] = n_added
            st['stats'].append({'id': v['id'], 'date': v['date'], 'added': n_added})
            print(f"{i+1}/{len(vids)} {v['date']} +{n_added}", flush=True)
        STATE.write_text(json.dumps(st, indent=1), encoding='utf-8')
    total = sum(v for v in st['done'].values() if isinstance(v, int))
    print(f'HARVEST_DIA_DONE: {total} predictions from {len(vids)} videos', flush=True)


if __name__ == '__main__':
    main()
