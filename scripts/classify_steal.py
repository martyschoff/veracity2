"""Work-stealing classify worker: pick next undone batch from classify_state_*.json.

Usage: python classify_steal.py --slot <name> [endpoint name]
Endpoint fixed by --ep index into ENDPOINTS in classify_worker.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.pipeline import call_llm  # noqa: E402
from scripts.classify_worker import SYSTEM, VALID, ENDPOINTS, load_state, save_state  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
PRED_FILE = DATA / "predictions.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", required=True)
    ap.add_argument("--ep", type=int, default=2)
    a = ap.parse_args()
    preds = json.load(open(PRED_FILE, encoding="utf-8"))["predictions"]
    batches = [preds[i:i + 8] for i in range(0, len(preds), 8)]
    spath = DATA / f"classify_state_steal_{a.slot}.json"
    st = load_state(spath)
    ep = ENDPOINTS[a.ep]
    t0 = time.time()
    while True:
        done = {}
        for f in DATA.glob("classify_state_*.json"):
            if f.suffix != ".json":
                continue
            for _ in range(5):
                try:
                    s = json.load(open(f, encoding="utf-8"))
                    done.update(s["results"])
                    break
                except (PermissionError, json.JSONDecodeError):
                    time.sleep(1)
        if not done:
            continue
        undone = [b for b in range(len(batches)) if str(b) not in done]
        if not undone:
            break
        b = undone[0]
        if str(b) in st["results"]:
            continue
        chunk = batches[b]
        lines = []
        for j, p in enumerate(chunk):
            lines.append(f"[{j}] speaker={p['individual_name']} date={p.get('date','')}\n"
                         f"claim: {p['claim']}\nexcerpt: {(p.get('transcript_excerpt') or '')[:600]}")
        parsed = None
        for attempt in range(3):
            resp = call_llm(SYSTEM, "\n\n".join(lines), max_tokens=3000, endpoints=[ep])
            if resp:
                m = re.search(r"\[.*\]", resp, re.S)
                if m:
                    try:
                        arr = json.loads(m.group(0))
                        if isinstance(arr, list) and len(arr) >= max(1, int(len(chunk) * 0.75)):
                            parsed = arr
                            break
                    except Exception:
                        pass
            time.sleep(3)
        if parsed is None:
            st["errors"].append({"batch": b, "err": "no parse"})
            save_state(st, spath)
            print(f"{a.slot} batch {b}: FAILED", flush=True)
            time.sleep(5)
            continue
        by_i = {}
        for o in parsed:
            try:
                by_i[int(o.get("i"))] = o
            except Exception:
                pass
        out = {}
        for j in range(len(chunk)):
            o = by_i.get(j)
            cls = str(o.get("class", "UNCLEAR")).upper().strip() if o else "UNCLEAR"
            cls = cls if cls in VALID else "UNCLEAR"
            out[str(j)] = {
                "pred_id": chunk[j]["id"],
                "class": cls,
                "claim": (o.get("claim") if o else None) or chunk[j]["claim"],
                "category": str(o.get("category", "other")).lower().strip() if o else "other",
                "reason": (o.get("reason", "") if o else "missing in LLM batch response"),
            }
        st["results"][str(b)] = out
        save_state(st, spath)
        if len(st["results"]) % 5 == 0:
            rate = len(st["results"]) / max(time.time() - t0, 1)
            print(f"{a.slot}: {len(st['results'])} stolen, {round(rate*60,1)}/min, "
                  f"remaining={len([x for x in undone if x != b])}", flush=True)
    print(f"{a.slot}: ALL DONE", flush=True)


if __name__ == "__main__":
    main()
