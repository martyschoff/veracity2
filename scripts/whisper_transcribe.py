"""Whisper transcription worker: transcribe the caption-blocked sources via the
big3080 whisper.cpp server (GPU 0, port 8080), then store transcripts in the
format the deepqa judge expects (ytdlp-<id>.md with '## Transcript').

Usage: python whisper_transcribe.py            # processes data/deepqa_fetch exceptions
State: data/whisper_state.json (survives crashes; incremental saves every result)
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
import uuid
from pathlib import Path

BASE = Path(r'C:/Users/schof/veracity2')
CACHE = Path(r'C:/Users/schof/AppData/Local/hermes/cache/web')
STATE = BASE / 'data' / 'whisper_state.json'
WHISPER = 'http://100.124.236.23:8080'

YTDLPS = [r'C:/Users/schof/AppData/Local/hermes/tools/python-3.14.7+20260901-win32-x64/Scripts/yt-dlp.exe']


def ytdlp_path():
    for p in YTDLPS:
        if Path(p).exists():
            return p
    return 'yt-dlp'


def load_exceptions() -> list:
    """Collect video ids whose deepqa fetch ended in exception."""
    ids = {}
    for f in sorted(BASE.glob('data/deepqa_fetch_state_*.json')):
        st = json.load(open(f, encoding='utf-8'))
        for vid, status in (st.get('done') or {}).items():
            if isinstance(status, str) and 'exc' in status:
                ids[vid] = f.name
            elif status is True and not (CACHE / f'ytdlp-{vid}.md').exists():
                pass
    # also the fetch missing list itself
    missing = BASE / 'data/deepqa_ids_missing.json'
    if missing.exists():
        for vid in json.load(open(missing, encoding='utf-8')):
            ids.setdefault(vid, 'missing')
    return sorted(ids)


def transcribe(vid: str) -> bool:
    """Download audio for vid, POST to whisper, write ytdlp-<id>.md."""
    tmp = Path(os.environ.get('TMPDIR', r'C:/Users/schof/AppData/Local/hermes/cache/scratch')) / f'wa_{vid}.m4a'
    if not tmp.exists():
        r = subprocess.run(
            [ytdlp_path(), '--extractor-args', 'youtube:player_client=android_vr',
             '-x', '--audio-format', 'mp3', '--audio-quality', '5',
             '-o', str(tmp).replace('.m4a', '.%(ext)s'),
             f'https://www.youtube.com/watch?v={vid}'],
            capture_output=True, text=True, timeout=600)
        # locate actual downloaded file
        found = list(tmp.parent.glob(f'wa_{vid}.*'))
        if not found:
            return False
        audio = found[0]
    else:
        audio = tmp

    # POST to whisper.cpp server
    boundary = uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{audio.name}"\r\n'
            f'Content-Type: application/octet-stream\r\n\r\n').encode() + audio.read_bytes() + \
           f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="response_format"\r\n\r\ntext\r\n--{boundary}--\r\n'.encode()
    req = urllib.request.Request(
        WHISPER + '/inference', data=body, method='POST',
        headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=900) as resp:
        text = resp.read().decode('utf-8', errors='replace')
    # write in the deepqa format
    out = (f"# Video {vid}\n**Uploaded at**: UNKNOWN\n## Transcript\n{text.strip()}\n")
    (CACHE / f'ytdlp-{vid}.md').write_text(out, encoding='utf-8')
    # cleanup audio
    try:
        audio.unlink()
    except OSError:
        pass
    print(f'{vid}: transcribed {time.time()-t0:.0f}s, {len(text)} chars', flush=True)
    return True


def main():
    st = json.load(open(STATE, encoding='utf-8')) if STATE.exists() else {'done': {}, 'failed': {}}
    ids = load_exceptions()
    todo = [v for v in ids if v not in st['done'] and v not in st['failed']]
    print(f'{len(todo)} videos to transcribe (of {len(ids)} candidates)', flush=True)
    for i, vid in enumerate(todo):
        try:
            ok = transcribe(vid)
            st['done'][vid] = True if ok else 'no-audio'
        except Exception as e:
            st['failed'][vid] = str(e)[:200]
            print(f'{vid}: FAILED {str(e)[:120]}', flush=True)
        STATE.write_text(json.dumps(st, indent=1), encoding='utf-8')
        if (i + 1) % 10 == 0:
            print(f'{i+1}/{len(todo)} processed', flush=True)
    print('WHISPER_SWEEP_DONE', len(st['done']), 'done,', len(st['failed']), 'failed', flush=True)


if __name__ == '__main__':
    main()
