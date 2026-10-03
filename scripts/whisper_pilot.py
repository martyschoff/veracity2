"""Whisper pilot: download audio for 3 blocked videos, transcribe via the 3080 node.

Usage: python scripts/whisper_pilot.py
Output: data/whisper_transcripts/<videoid>.txt + pilot results printed.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "whisper_transcripts"
OUT.mkdir(exist_ok=True)
CACHE = Path(r"C:/Users/schof/AppData/Local/hermes/cache/web")
WHISPER_URL = "http://100.124.236.23:8080/inference"


def fetch_audio(vid: str) -> Path | None:
    out = CACHE / f"audio_{vid}.mp3"
    if out.exists() and out.stat().st_size > 10000:
        return out
    url = f"https://www.youtube.com/watch?v={vid}"
    r = subprocess.run(
        [r"C:/Users/schof/AppData/Local/hermes/tools/python-3.14.7+20260901-win32-x64/Scripts/yt-dlp.exe", "-x", "--audio-format", "mp3", "--audio-quality", "5",
         "-o", str(out), "--no-playlist", url],
        capture_output=True, text=True, timeout=900,
    )
    if out.exists() and out.stat().st_size > 10000:
        return out
    print(f"  audio fetch failed for {vid}: {r.stderr[-150:] if r.stderr else ''}")
    return None


def transcribe(mp3: Path) -> str | None:
    r = subprocess.run(
        ["curl", "-s", "-m", "900", "-X", "POST", WHISPER_URL,
         "-F", f"file=@{mp3}", "-F", "response_format=json"],
        capture_output=True, text=True, timeout=960,
    )
    try:
        return json.loads(r.stdout).get("text")
    except Exception:
        print(f"  transcribe failed: {r.stdout[:150]}")
        return None


def main():
    ids = json.load(open(BASE / "data" / "whisper_pilot_ids.json", encoding="utf-8"))
    ok, fail = 0, 0
    for vid in ids:
        print(f"[{vid}] fetching audio...", flush=True)
        mp3 = fetch_audio(vid)
        if not mp3:
            fail += 1
            continue
        print(f"[{vid}] transcribing ({mp3.stat().st_size//1024}KB)...", flush=True)
        text = transcribe(mp3)
        if text:
            (OUT / f"{vid}.txt").write_text(text, encoding="utf-8")
            ok += 1
            print(f"[{vid}] OK: {text[:120]}...", flush=True)
        else:
            fail += 1
    print(f"PILOT DONE: ok={ok} fail={fail}", flush=True)


if __name__ == "__main__":
    main()
