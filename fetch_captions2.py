"""Fetch YouTube transcripts + upload date via yt-dlp; write backfill3-format cache files.

Usage: python fetch_captions2.py ID1 ID2 ...
Writes C:/Users/schof/AppData/Local/hermes/cache/web/ytdlp-<ID>.md
"""
import sys, os, json, re

CACHE = r"C:/Users/schof/AppData/Local/hermes/cache/web"


def vtt_to_text(vtt):
    out = []
    for line in vtt.splitlines():
        if ("-->" in line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))
                or re.match(r"^\d+$", line.strip())):
            continue
        t = re.sub(r"</?c[^>]*>", "", line).strip()
        if t and (not out or out[-1] != t):
            out.append(t)
    return " ".join(out)


def fetch(vid):
    import yt_dlp
    opts = {
        "skip_download": True,
        "writesubtitles": True, "writeautomaticsub": True,
        "extractor_args": {"youtube": {"player_client": ["android_vr"]}},
        "subtitleslangs": ["en", "en-orig"],
        "subtitlesformat": "vtt",
        "quiet": True,
        "no_warnings": True,
        "outtmpl": os.path.join(CACHE, f"ytdlp_%(id)s"),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=True)
    date = info.get("upload_date")
    date = f"{date[:4]}-{date[4:6]}-{date[6:]}" if date else ""
    title = info.get("title", "")
    if date and date < "2024-04-30":
        md = (f"# [{title}](https://www.youtube.com/watch?v={vid})\n\n"
              f"**Uploaded at**: {date}\n\n## Transcript\n\n[pre-cutoff]\n")
        open(os.path.join(CACHE, f"ytdlp-{vid}.md"), "w", encoding="utf-8").write(md)
        return date, -1, title
    # find written subtitle file
    sub = None
    for f in os.listdir(CACHE):
        if f.startswith(f"ytdlp_{vid}.") and f.endswith(".vtt"):
            sub = os.path.join(CACHE, f)
    if sub:
        text = vtt_to_text(open(sub, encoding="utf-8", errors="replace").read())
        os.remove(sub)
    else:
        # fall back to description-less: use automatic_captions? not retained
        text = ""
    if len(text) < 200:
        return date, 0, title
    md = (f"# [{title}](https://www.youtube.com/watch?v={vid})\n\n"
          f"**Uploaded at**: {date}\n\n## Transcript\n\n{text}\n")
    open(os.path.join(CACHE, f"ytdlp-{vid}.md"), "w", encoding="utf-8").write(md)
    return date, len(text), title


if __name__ == "__main__":
    import time
    for vid in sys.argv[1:]:
        vid = vid.strip()
        if not vid:
            continue
        for attempt in range(3):
            try:
                date, n, title = fetch(vid)
                if n == -1:
                    print(vid, "OLD", date, flush=True)
                    break
                if n >= 200:
                    print(vid, "OK", date, n, title[:50], flush=True)
                    break
                print(vid, "FAIL", date, n, title[:50], flush=True)
                time.sleep(20)
            except Exception as e:
                msg = str(e)
                print(vid, "ERR", msg[:120], flush=True)
                if "429" in msg:
                    time.sleep(45)
                else:
                    break
        time.sleep(2)
