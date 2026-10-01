"""Fetch YouTube captions via invidious.f5.si and write cache-format .md files.

Usage: python fetch_captions.py ID1 ID2 ...
Writes C:/Users/schof/AppData/Local/hermes/cache/web/invidious-<ID>.md with
'**Uploaded at**: <date>' and '## Transcript' sections (backfill3.py format).
Prints OK/FAIL per id.
"""
import sys, os, json, re, datetime
import urllib.request, urllib.parse

CACHE = r"C:/Users/schof/AppData/Local/hermes/cache/web"
BASES = ["https://invidious.f5.si", "https://invidious.nerdvpn.de"]


def get(url, timeout=30):
    import subprocess
    r = subprocess.run(["curl", "-s", "-m", str(timeout), url],
                       capture_output=True, text=True, timeout=timeout + 10)
    return r.stdout


def vtt_to_text(vtt):
    lines = []
    for line in vtt.splitlines():
        if ("-->" in line or line.startswith(("WEBVTT", "Kind:", "Language:", "NOTE"))
                or re.match(r"^\d+$", line.strip())):
            continue
        t = line.strip()
        if t and (not lines or lines[-1] != t):
            lines.append(t)
    # de-dupe rolling captions
    out = []
    for t in lines:
        if not out or out[-1] != t:
            out.append(t)
    return " ".join(out)


def fetch(vid):
    import time
    err = 'all-bases-failed'
    for base in BASES:
        for attempt in range(3):
            try:
                caps = json.loads(get(f"{base}/api/v1/captions/{vid}"))
                if not caps.get("captions"):
                    err = 'no-captions'
                    break
                cap = caps["captions"][0]
                time.sleep(1.5)
                vtt = get(base + cap["url"])
                text = vtt_to_text(vtt)
                if len(text) < 200:
                    err = 'short-transcript'
                    continue
                date = ""
                title = ""
                try:
                    time.sleep(1.0)
                    meta = json.loads(get(f"{base}/api/v1/videos/{vid}"))
                    date = (meta.get("publishedText") or "")
                    pub = meta.get("published")
                    if pub:
                        date = datetime.datetime.utcfromtimestamp(int(pub)).strftime("%Y-%m-%d")
                    title = meta.get("title", "")
                except Exception:
                    pass
                md = (f"# [{title}](https://www.youtube.com/watch?v={vid})\n\n"
                      f"**Uploaded at**: {date}\n\n## Transcript\n\n{text}\n")
                path = os.path.join(CACHE, f"invidious-{vid}.md")
                open(path, "w", encoding="utf-8").write(md)
                return date, len(text)
            except Exception as e:
                err = str(e)[:80]
                time.sleep(3)
    return None, err


if __name__ == "__main__":
    for vid in sys.argv[1:]:
        date, n = fetch(vid)
        print(vid, "OK" if date is not None else "FAIL", date, n)
