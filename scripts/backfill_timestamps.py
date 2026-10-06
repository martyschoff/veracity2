"""Timestamp backfill: match each prediction's transcript_excerpt to a word
timestamp in the source video's YouTube auto-subs, storing t_seconds.

Resumable: state in data/ts_state.json, incremental saves.
"""
import json
import re
import subprocess
import urllib.parse
from pathlib import Path

BASE = Path(r'C:/Users/schof/veracity2')
STATE = BASE / 'data' / 'ts_state.json'
YTDLP = r'C:/Users/schof/AppData/Local/hermes/tools/python-3.14.7+20260901-win32-x64/Scripts/yt-dlp.exe'
TMP = Path(r'C:/Users/schof/AppData/Local/hermes/cache/scratch')


def vid_of(url: str):
    m = re.search(r'(?:v=|youtu\.be/|shorts/)([\w-]{11})', url or '')
    return m.group(1) if m else None


def word_map(vid: str):
    """Fetch auto-subs for vid; return list of (seconds, word)."""
    vttf = TMP / f'ts_{vid}.en.vtt'
    if not vttf.exists():
        r = subprocess.run(
            [YTDLP, '--extractor-args', 'youtube:player_client=android_vr',
             '--skip-download', '--write-auto-subs', '--sub-langs', 'en',
             '--sub-format', 'vtt', '-o', str(TMP / f'ts_{vid}'),
             f'https://www.youtube.com/watch?v={vid}'],
            capture_output=True, text=True, timeout=120)
        found = list(TMP.glob(f'ts_{vid}*.vtt'))
        if not found:
            return None
        vttf = found[0]
    vtt = vttf.read_text(encoding='utf-8', errors='replace')
    words, cur = [], 0.0
    for line in vtt.splitlines():
        m = re.match(r'(\d+):(\d+):([\d.]+) -->', line)
        if m:
            cur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
            continue
        for mm in re.finditer(r'<(\d+):(\d+):([\d.]+)>(?:<c>)?\s*([\w\']+)', line):
            t = int(mm.group(1)) * 3600 + int(mm.group(2)) * 60 + float(mm.group(3))
            words.append((t, mm.group(4).lower()))
    return words or None


def norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", '', w.lower())


def find_time(words, excerpt: str, claim: str = ''):
    """Match the longest run of excerpt words inside the word map."""
    # build target from excerpt tail (excerpts often start mid-sentence)
    target = [norm(w) for w in re.findall(r"[\w']+", excerpt or claim) if norm(w)]
    if len(target) < 6:
        return None
    seqs = [target[i:i + 8] for i in range(0, max(1, len(target) - 7), 3)]
    wtext = [w for _, w in words]
    best = None
    for seq in seqs:
        if len(seq) < 5:
            continue
        n = len(seq)
        for i in range(len(wtext) - n):
            if wtext[i:i + n] == seq:
                best = words[i][0]
                break
        if best is not None:
            return best
    # fallback: try shorter 5-word windows
    for i in range(0, max(1, len(target) - 4), 2):
        seq = target[i:i + 5]
        n = len(seq)
        for j in range(len(wtext) - n):
            if wtext[j:j + n] == seq:
                return words[j][0]
    return None


def main():
    st = json.load(open(STATE, encoding='utf-8')) if STATE.exists() else {'done': {}, 'novtt': [], 'nomatch': []}
    d = json.load(open(BASE / 'data' / 'predictions.json', encoding='utf-8'))
    preds = d['predictions']
    # group by video
    byvid = {}
    for p in preds:
        if p.get('t_seconds') is not None:
            continue
        vid = vid_of(p.get('source_url', ''))
        if vid:
            byvid.setdefault(vid, []).append(p)
    todo = [v for v in byvid if v not in st['done']]
    print(f'{len(todo)} videos to process ({sum(len(byvid[v]) for v in todo)} predictions)', flush=True)
    for i, vid in enumerate(todo):
        try:
            words = word_map(vid)
            if not words:
                st['novtt'].append(vid)
                st['done'][vid] = 'novtt'
            else:
                hits = 0
                for p in byvid[vid]:
                    t = find_time(words, p.get('transcript_excerpt') or '', p.get('claim') or '')
                    if t is not None:
                        p['t_seconds'] = int(t)
                        hits += 1
                st['done'][vid] = hits
        except Exception as e:
            st.setdefault('errors', {})[vid] = str(e)[:150]
            st['done'][vid] = 'error'
        st['_saved'] = len(st['done'])
        STATE.write_text(json.dumps(st), encoding='utf-8')
        if hits_total := st['done'].get(vid):
            if isinstance(hits_total, int) and hits_total:
                # save predictions incrementally every 10 videos
                pass
        if (i + 1) % 10 == 0:
            json.dump(d, open(BASE / 'data' / 'predictions.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
            print(f'{i + 1}/{len(todo)} videos, hits so far: '
                  f'{sum(v for v in st["done"].values() if isinstance(v, int))}', flush=True)
    json.dump(d, open(BASE / 'data' / 'predictions.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
    hits = sum(v for v in st['done'].values() if isinstance(v, int))
    print(f'TS_BACKFILL_DONE: {hits} predictions timestamped, '
          f'{len(st["novtt"])} no-subs, {len(st.get("errors", {}))} errors', flush=True)


if __name__ == '__main__':
    main()
