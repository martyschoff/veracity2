"""Task A sharded worker: classify batches with stride 3 across 3 LLM endpoints."""
import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.pipeline import call_llm  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
PRED_FILE = DATA / "predictions.json"

SYSTEM = (
    "You are a strict data-quality classifier for a prediction-tracking site. "
    "You will be given numbered text blocks, each a claim attributed to a public figure. "
    "Classify each block into EXACTLY ONE class:\n"
    "- PREDICTION: a forward-looking claim about WORLD OUTCOMES (markets, geopolitics, "
    "economy, technology, energy, war, health/longevity breakthroughs for humanity, etc.) "
    "that the figure owns/asserts. Must be testable as right/wrong later.\n"
    "- PERSONAL: about their own body, health regimen, family, or lifestyle "
    "(e.g. 'I'll report back in six months' about their own testosterone regimen).\n"
    "- SELF-REPORT: describing past or present events they did or observed; not forward-looking.\n"
    "- PERSONAL-POSITION: their own investments/positions ('I'm overweight gold', 'I bought X').\n"
    "- ADVICE: telling listeners/readers what to do ('investors should hold cash', "
    "'you should take X supplement'). Exhortations without a world forecast.\n"
    "- PROMO: promoting their own products, companies, books, subscriptions, events.\n"
    "- UNCLEAR: cannot tell.\n"
    "SPLIT RULE: if a block compounds a personal/position/advice part WITH a world-outcome "
    "forecast, class it PREDICTION and return a REVISED 'claim' containing ONLY the "
    "world-outcome forecast part (drop the personal/investment/advice part). Example: "
    "'I'm buying gold because it goes to $8,000' -> PREDICTION, claim 'Gold goes to $8,000'.\n"
    "If the block is kept as-is, 'claim' should be the original text unchanged.\n"
    "Also re-derive a sensible category from the claim text from this list: ai, finance, "
    "geopolitics, energy, china, ukraine, health, other. (Fix nonsense categories like a "
    "health claim filed under 'ai'.)\n"
    "Return ONLY a JSON array, one object per input block, in the same order: "
    '[{"i": <input index number>, "class": "...", "claim": "...", "category": "...", "reason": "..."}]'
)

VALID = {"PREDICTION", "PERSONAL", "SELF-REPORT", "PERSONAL-POSITION", "ADVICE", "PROMO", "UNCLEAR"}
ENDPOINTS = [
    {"url": "http://100.84.167.88:11434/v1/chat/completions", "key": None, "model": "qwen3:32b"},
    {"url": "http://127.0.0.1:18434/v1/chat/completions", "key": "OyISwmqwQMak4mEOtO3zajuzSY8clG73",
     "model": "Qwen3.8-27B-UD-Q4_K_M"},
    {"url": "http://upthread64.tail5b3b50.ts.net:11434/v1/chat/completions", "key": None,
     "model": "qwen3-coder:30b-32k"},
]


def load_state(path):
    if path.exists():
        return json.load(open(path, encoding="utf-8"))
    return {"batch_idx": 0, "results": {}, "errors": []}


def save_state(st, path):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1), encoding="utf-8")
    tmp.replace(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--stride", type=int, default=3)
    a = ap.parse_args()
    preds = json.load(open(PRED_FILE, encoding="utf-8"))["predictions"]
    batches = [preds[i:i + 8] for i in range(0, len(preds), 8)]
    my_batches = list(range(a.shard, len(batches), a.stride))
    spath = DATA / f"classify_state_{a.shard}.json"
    st = load_state(spath)
    ep = ENDPOINTS[a.shard]
    t0 = time.time()
    for b in my_batches:
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
            print(f"s{a.shard} batch {b}: FAILED", flush=True)
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
        st["batch_idx"] = b + a.stride
        save_state(st, spath)
        done = len(st["results"]) + a.shard
        if len(st["results"]) % 5 == 0:
            print(f"s{a.shard}: {len(st['results'])}/{len(my_batches)} batches, "
                  f"{round((time.time()-t0)/60,1)} min", flush=True)
    print(f"s{a.shard}: DONE {len(st['results'])}/{len(my_batches)} errors={len(st['errors'])}", flush=True)


if __name__ == "__main__":
    main()
