"""Backfill predictions from cached YouTube transcript pages.

Usage:
  python backfill3.py process <channel> <id1> <id2> ...   # process given video ids using cache/web/*.md files
  python backfill3.py merge                              # merge results into data/predictions.json + render
Fetches are NOT done here; the agent fetches via web_extract which caches full
pages under C:/Users/schof/AppData/Local/hermes/cache/web/.
"""
import json, os, re, sys, glob, hashlib, datetime, threading

ROOT = r"C:/Users/schof/veracity2"
CACHE = r"C:/Users/schof/AppData/Local/hermes/cache/web"
STATE = os.path.join(ROOT, "backfill_state.json")
RESULTS = os.path.join(ROOT, "backfill_results.jsonl")

CATS = {
    "ZeihanonGeopolitics": ("Peter Zeihan", ["geopolitics", "energy", "china", "ukraine", "finance"]),
    "GZEROMedia": ("Ian Bremmer", ["geopolitics"]),
    "PeterHDiamandis": ("Peter Diamandis", ["ai"]),
}
BREMMER_OK = re.compile(r"quick take|ian explains|ask ian", re.I)


def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE))
    return {"processed": {}}


def find_cache(vid):
    for f in glob.glob(os.path.join(CACHE, "www.youtube.com-*.md")):
        try:
            t = open(f, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if vid in t:
            return f, t
    return None, None


def parse_page(text):
    m = re.search(r"\*\*Uploaded at\*\*: (\d{4}-\d{2}-\d{2})", text)
    date = m.group(1) if m else None
    m2 = re.search(r"^## Transcript\s*\n(.*)$", text, re.S | re.M)
    trans = m2.group(1).strip() if m2 else ""
    return date, trans


def process(channel, vids):
    sys.path.insert(0, ROOT)
    from src.pipeline import extract_predictions
    from src.pipeline import strip_quotes  # noqa: F401  (used inside extract_predictions)
    author, cats = CATS[channel]
    queue = {v["id"]: v for v in json.load(open(os.path.join(ROOT, "work_queue.json")))[channel]}
    state = load_state()
    preds = json.load(open(os.path.join(ROOT, "data/predictions.json")))
    existing_urls = set(x.get("source_url", "") for x in preds["predictions"])
    added, results = 0, []
    from concurrent.futures import ThreadPoolExecutor
    state_lock = threading.Lock()
    out_lock = threading.Lock()

    def work(vid):
        url = f"https://www.youtube.com/watch?v={vid}"
        meta = queue.get(vid, {})
        title = meta.get("title", "")
        if channel == "GZEROMedia" and not BREMMER_OK.search(title):
            with state_lock:
                state["processed"][vid] = 0
            return {"id": vid, "status": "SKIP_TITLE"}
        f, text = find_cache(vid)
        if not text:
            return {"id": vid, "status": "NO_CACHE"}
        up_date, trans = parse_page(text)
        date = up_date or meta.get("date")
        if not trans or len(trans) < 200:
            with state_lock:
                state["processed"][vid] = 0
            with open(os.path.join(ROOT, "no_transcript.txt"), "a") as nf:
                nf.write(f"{vid} {channel}\n")
            return {"id": vid, "status": "NO_TRANSCRIPT", "date": date}
        new = extract_predictions(trans, url, author, cats, date)
        kept = 0
        out = []
        for p in new[:2]:
            p["id"] = f"pred_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{vid[:6]}_{kept}"
            p["test_status"] = "eligible"
            p["testing_since"] = date
            out.append({"id": vid, "status": "OK", "date": date, "pred": p})
            kept += 1
        with state_lock:
            state["processed"][vid] = kept
            json.dump(state, open(STATE, "w"))
        return out

    todo = [v for v in vids if v not in state["processed"]
            and f"https://www.youtube.com/watch?v={v}" not in existing_urls]
    results = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        for res in ex.map(work, todo):
            if isinstance(res, list):
                results.extend(res)
                for r in res:
                    print("  +", r["date"], r["pred"]["claim"][:90], flush=True)
            elif res:
                results.append(res)
                print("  -", res["id"], res["status"], flush=True)
    with open(RESULTS, "a", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r) + "\n")
    print(f"channel={channel} requested={len(vids)} predictions={sum(1 for r in results if r['status']=='OK')} total_state={len(state['processed'])}")


def merge():
    preds = json.load(open(os.path.join(ROOT, "data/predictions.json")))
    existing_urls = set(x.get("source_url", "") for x in preds["predictions"])
    existing_ids = set(x["id"] for x in preds["predictions"])
    n = 0
    if os.path.exists(RESULTS):
        for line in open(RESULTS, encoding="utf-8"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            p = r.get("pred")
            if not p or r.get("merged"):
                continue
            if p["source_url"] in existing_urls or p["id"] in existing_ids:
                continue
            preds["predictions"].append(p)
            existing_urls.add(p["source_url"])
            existing_ids.add(p["id"])
            n += 1
    # mark merged
    if os.path.exists(RESULTS):
        lines = []
        for line in open(RESULTS, encoding="utf-8"):
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("pred") and not r.get("merged"):
                r["merged"] = True
            lines.append(json.dumps(r))
        open(RESULTS, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    json.dump(preds, open(os.path.join(ROOT, "data/predictions.json"), "w"), indent=1)
    print(f"merged {n}; total {len(preds['predictions'])}")


def deploy():
    import subprocess
    env = dict(os.environ, SURGE_TOKEN="ea807c6f912951573c26c7fed2788f3f")
    subprocess.run(["python", "render.py"], cwd=ROOT, check=True)
    subprocess.run(["surge", "surge_dist/", "veracity2.surge.sh"], cwd=ROOT, check=True, env=env)
    subprocess.run(["git", "add", "-A"], cwd=ROOT)
    subprocess.run(["git", "commit", "-m", "backfill: zeihan/bremmer/diamandis predictions"], cwd=ROOT)
    subprocess.run(["git", "push"], cwd=ROOT)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "process":
        process(sys.argv[2], sys.argv[3:])
    elif cmd == "merge":
        merge()
    elif cmd == "deploy":
        deploy()
