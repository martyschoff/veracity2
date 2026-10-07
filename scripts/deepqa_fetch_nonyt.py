# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Deep QA fetch for non-YouTube sources (Doomberg substack, mcalvany.com)."""
import hashlib
import json
import re
import time
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "deepqa_nonyt"
OUT.mkdir(exist_ok=True)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/147.0 Safari/537.36"}


def extract(html):
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;|&#160;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def main():
    preds = json.load(open(BASE / "data" / "predictions.json", encoding="utf-8"))["predictions"]
    urls = sorted({p["source_url"] for p in preds
                   if "youtube" not in (p.get("source_url") or "")
                   and len(p.get("transcript_excerpt") or "") < 200})
    print(f"{len(urls)} unique urls")
    stf = BASE / "data" / "deepqa_fetch_nonyt_state.json"
    st = json.load(open(stf, encoding="utf-8")) if stf.exists() else {"done": {}}
    for n, u in enumerate(urls):
        if u in st["done"]:
            continue
        h = hashlib.md5(u.encode()).hexdigest()[:12]
        f = OUT / f"{h}.txt"
        try:
            r = httpx.get(u, headers=UA, timeout=60, follow_redirects=True)
            if r.status_code == 200 and len(r.text) > 5000:
                f.write_text(f"URL: {u}\n\n{extract(r.text)}", encoding="utf-8")
                st["done"][u] = "ok"
            else:
                st["done"][u] = f"http_{r.status_code}"
        except Exception as e:
            st["done"][u] = f"exc:{str(e)[:80]}"
        stf.write_text(json.dumps(st, indent=1), encoding="utf-8")
        print(n + 1, st["done"][u], u[:70], flush=True)
        time.sleep(0.5)
    print("NONYT FETCH DONE", flush=True)


if __name__ == "__main__":
    main()
