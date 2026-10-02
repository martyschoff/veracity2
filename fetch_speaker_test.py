"""Fetch test transcripts (side files only — never touches predictions.json)."""
import json
import os
import subprocess

VIDS = [
    ("eWTfjnkaH0c", "moonshots_susskind"),
    ("LN92sWO2i9U", "moonshots_housel"),
    ("WsyPVdDjs2Y", "zeihan_solo"),
]
OUT = "data/speaker_test"
os.makedirs(OUT, exist_ok=True)

for vid, name in VIDS:
    print(f"=== {name} ({vid})")
    meta = subprocess.run(
        ["python", "-m", "yt_dlp", "--extractor-args", "youtube:player_client=android_vr",
         "--skip-download", "--write-auto-subs", "--sub-langs", "en.*", "--sub-format", "vtt/srt/best",
         "-o", f"{OUT}/{name}", "--print-json", f"https://www.youtube.com/watch?v={vid}"],
        capture_output=True, text=True, timeout=300)
    try:
        j = json.loads(meta.stdout.strip().splitlines()[-1])
        info = {"id": vid, "title": j.get("title"), "upload_date": j.get("upload_date"),
                "channel": j.get("channel"), "description": (j.get("description") or "")[:3000]}
        json.dump(info, open(f"{OUT}/{name}_meta.json", "w"), indent=1)
        print(info["title"], info["upload_date"])
    except Exception as e:
        print("META FAIL", e, meta.stdout[-300:], meta.stderr[-300:])
    print(subprocess.run(["ls", OUT], capture_output=True, text=True).stdout)
