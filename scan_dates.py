# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Scan upload dates for video ids via yt-dlp metadata (no captions).

Usage: python scan_dates.py ID1 ID2 ...   (appends to dates.json)
"""
import sys, os, json

ROOT = r"C:/Users/schof/veracity2"
DATES = os.path.join(ROOT, "dates.json")
try:
    dates = json.load(open(DATES))
except Exception:
    dates = {}

import yt_dlp
opts = {"skip_download": True, "quiet": True, "no_warnings": True,
        "extractor_args": {"youtube": {"player_client": ["android_vr"]}}}
with yt_dlp.YoutubeDL(opts) as ydl:
    for vid in sys.argv[1:]:
        if vid in dates:
            continue
        try:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
            dates[vid] = info.get("upload_date") or ""
        except Exception as e:
            dates[vid] = "ERR:" + str(e)[:60]
        if len(dates) % 20 == 0:
            json.dump(dates, open(DATES, "w"))
            print(f"  saved {len(dates)}", flush=True)
json.dump(dates, open(DATES, "w"))
old = sum(1 for v in dates.values() if v and v < "20240430")
print(f"done: {len(dates)} scanned, {old} pre-cutoff", flush=True)
