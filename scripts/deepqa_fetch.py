# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Deep QA fetch: download full YouTube transcripts (android_vr path) for missing ids.

Usage: python deepqa_fetch.py --shard K [--stride N]
Ids list: data/deepqa_ids_missing.json (JSON array). Cache: ytdlp-<id>.md in web cache.
State: data/deepqa_fetch_state_<shard>.json
"""
import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent.parent
CACHE = r"C:/Users/schof/AppData/Local/hermes/cache/web"

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/147.0 Safari/537.36"}


def vtt_to_text(vtt):
    out = []
    for line in vtt.splitlines():
        line = line.strip()
        if (not line or "-->" in line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))
                or re.match(r"^\d+$", line)):
            continue
        t = re.sub(r"<[^>]+>", "", line).strip()
        if out and out[-1] == t:
            continue
        out.append(t)
    return " ".join(out)


def fetch_one(vid):
    import subprocess
    out = Path(CACHE) / f"ytdlp-{vid}.md"
    p = subprocess.run(["python", "-m", "yt_dlp", "-J", "--skip-download",
                        "--extractor-args", "youtube:player_client=android_vr",
                        f"https://www.youtube.com/watch?v={vid}"],
                       capture_output=True, text=True, timeout=300)
    if p.returncode != 0 or not p.stdout.strip():
        return "ytdlp_fail", (p.stderr or "")[-300:]
    lines = [l for l in p.stdout.strip().splitlines() if l.strip()]
    try:
        j = json.loads(lines[-1])
    except Exception:
        return "json_fail", ""
    caps = j.get("automatic_captions") or {}
    subs = j.get("subtitles") or {}
    track = ((subs.get("en") or [None])[0] or (caps.get("en-orig") or caps.get("en")
            or caps.get("en-US") or [None])[0])
    date = j.get("upload_date") or ""
    date = f"{date[:4]}-{date[4:6]}-{date[6:]}" if date else ""
    title = (j.get("title") or "").replace("|", "-")
    if not track:
        md = (f"# [{title}](https://www.youtube.com/watch?v={vid})\n\n"
              f"**Uploaded at**: {date}\n\n## Transcript\n\n[no-track]\n")
        out.write_text(md, encoding="utf-8")
        return "no_track", ""
    url = [t for t in track if t["ext"] == "vtt"][0]["url"]
    got = None
    for attempt in range(5):
        try:
            r = httpx.get(url, headers=UA, timeout=60, follow_redirects=True)
            if r.status_code == 200:
                got = r.text
                break
        except Exception:
            pass
        time.sleep(10 + random.random() * 15)
    if not got:
        out.write_text(f"# [{title}](https://www.youtube.com/watch?v={vid})\n\n"
                       f"**Uploaded at**: {date}\n\n## Transcript\n\n[no-track]\n", encoding="utf-8")
        return "http_fail", ""
    text = vtt_to_text(got)
    md = (f"# [{title}](https://www.youtube.com/watch?v={vid})\n\n"
          f"**Uploaded at**: {date}\n\n## Transcript\n\n{text}\n")
    out.write_text(md, encoding="utf-8")
    return ("ok", "") if len(text) > 500 else ("short", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--stride", type=int, default=2)
    a = ap.parse_args()
    ids = json.load(open(BASE / "data" / "deepqa_ids_missing.json", encoding="utf-8"))
    mine = ids[a.shard::a.stride]
    stf = BASE / "data" / f"deepqa_fetch_state_{a.shard}.json"
    st = {"done": {}, "counts": {}}
    if stf.exists():
        st = json.load(open(stf, encoding="utf-8"))
    t0 = time.time()
    for n, vid in enumerate(mine):
        if vid in st["done"]:
            continue
        try:
            status, err = fetch_one(vid)
        except Exception as e:
            status, err = "exc", str(e)[:200]
        st["done"][vid] = status
        st["counts"][status] = st["counts"].get(status, 0) + 1
        if err:
            (BASE / "data" / f"deepqa_fetch_err_{a.shard}.log").open("a").write(f"{vid} {err}\n")
        if (n + 1) % 5 == 0:
            stf.write_text(json.dumps(st, indent=1), encoding="utf-8")
            rate = (n + 1) / max(time.time() - t0, 1)
            print(f"s{a.shard}: {n+1}/{len(mine)} {st['counts']} {round(rate*60,1)}/min", flush=True)
        time.sleep(1 + random.random() * 2)
    stf.write_text(json.dumps(st, indent=1), encoding="utf-8")
    print(f"s{a.shard}: DONE {st['counts']}", flush=True)


if __name__ == "__main__":
    main()
