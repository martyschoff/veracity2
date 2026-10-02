import sys
sys.path.insert(0, r"C:/Users/schof/veracity2/scripts")
from concurrent.futures import ThreadPoolExecutor
import json, threading, time
import mcalvany_extract as m

content = json.load(open(r"C:/Users/schof/veracity2/data/mcalvany_wc_content.json"))
OUT = r"C:/Users/schof/veracity2/data/mcalvany_wc_extractions.json"
lock = threading.Lock()
results = json.load(open(OUT)) if __import__('os').path.exists(OUT) else []
done = {r["post_id"] for r in results}
d = json.load(open(m.DATA, encoding="utf-8"))
done_urls = {p["source_url"] for p in d["predictions"] if p["individual_name"] == "David McAlvany"}

def work(pid):
    p = content[pid]
    if p["link"] in done_urls or pid in done:
        return
    text = m.clean(p["content"]["rendered"])
    i = text.find("Welcome to the McAlvany Weekly Commentary")
    if i > 0: text = text[i:]
    text = text[:14000]
    items = []
    for _ in range(3):
        try:
            raw = m.call_llm(m.PROMPT.format(date=p["date"][:10], text=text))
            items = [x for x in m.parse_items(raw)[:2] if m.year_filter(x["claim"], p["date"])]
            break
        except Exception as e:
            print("ERR", pid, e, flush=True); time.sleep(10)
    rec = {"post_id": pid, "date": p["date"][:10], "url": p["link"], "title": p["title"]["rendered"], "predictions": items}
    with lock:
        results.append(rec)
        json.dump(results, open(OUT, "w"), indent=1)
    print("DONE", p["date"][:10], len(items), flush=True)

ids = sorted(content.keys(), key=lambda k: content[k]["date"], reverse=True)
with ThreadPoolExecutor(4) as ex:
    list(ex.map(work, ids))
print("ALL DONE", len(results), flush=True)
