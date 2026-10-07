# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Task A: classify every block in data/predictions.json via LLM batches of 8.

PREDICTION blocks stay (with re-derived category, possibly revised claim after
split rule). Everything else moves to data/guest_pool.json.
State/checkpoint: data/deep_qa_state.json
"""
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.pipeline import call_llm, LLM_ENDPOINTS  # noqa: E402

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
PRED_FILE = DATA / "predictions.json"
POOL_FILE = DATA / "guest_pool.json"
STATE_FILE = DATA / "deep_qa_state.json"
NIMO = LLM_ENDPOINTS[1]

CLASSES = ["PREDICTION", "PERSONAL", "SELF-REPORT", "PERSONAL-POSITION", "ADVICE", "PROMO", "UNCLEAR"]

EXTRA_CATS = {"ai", "finance", "geopolitics", "energy", "china", "ukraine", "health", "other"}

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


def load_state():
    if STATE_FILE.exists():
        return json.load(open(STATE_FILE, encoding="utf-8"))
    return {"stage": "A", "batch_idx": 0, "results": [], "errors": []}


def save_state(st):
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1), encoding="utf-8")
    tmp.replace(STATE_FILE)


def main():
    d = json.load(open(PRED_FILE, encoding="utf-8"))
    preds = d["predictions"]
    st = load_state()
    done = {r["i"] for r in st["results"]}
    batches = [preds[i:i + 8] for i in range(0, len(preds), 8)]
    print(f"total={len(preds)} batches={len(batches)} classified={len(done)}", flush=True)

    for b in range(st["batch_idx"], len(batches)):
        chunk = batches[b]
        lines = []
        for j, p in enumerate(chunk):
            lines.append(f"[{j}] speaker={p['individual_name']} date={p.get('date','')}\n"
                         f"claim: {p['claim']}\nexcerpt: {(p.get('transcript_excerpt') or '')[:600]}")
        user = "\n\n".join(lines)
        parsed = None
        for attempt in range(3):
            resp = call_llm(SYSTEM, user, max_tokens=3000, endpoints=[NIMO])
            if not resp:
                time.sleep(5)
                continue
            m = re.search(r"\[.*\]", resp, re.S)
            if not m:
                continue
            try:
                arr = json.loads(m.group(0))
                if isinstance(arr, list) and len(arr) >= len(chunk) * 0.75:
                    parsed = arr
                    break
            except Exception:
                continue
        if parsed is None:
            st["errors"].append({"batch": b, "err": "no parse after retries"})
            st["batch_idx"] = b
            save_state(st)
            print(f"batch {b}: FAILED, saved state", flush=True)
            time.sleep(10)
            continue

        by_i = {}
        for o in parsed:
            try:
                by_i[int(o.get("i"))] = o
            except Exception:
                pass
        for j in range(len(chunk)):
            if j in by_i:
                o = by_i[j]
                st["results"].append({
                    "i": len(st["results"]),
                    "pred_id": chunk[j]["id"],
                    "class": str(o.get("class", "UNCLEAR")).upper().strip(),
                    "claim": o.get("claim") or chunk[j]["claim"],
                    "category": str(o.get("category", "other")).lower().strip(),
                    "reason": o.get("reason", ""),
                })
            else:
                st["results"].append({"i": len(st["results"]), "pred_id": chunk[j]["id"],
                                      "class": "UNCLEAR", "claim": chunk[j]["claim"],
                                      "category": chunk[j].get("category", "other"),
                                      "reason": "missing in LLM batch response"})
        st["batch_idx"] = b + 1
        save_state(st)
        if (b + 1) % 10 == 0:
            print(f"batch {b + 1}/{len(batches)} done, results={len(st['results'])}", flush=True)

    print("CLASSIFICATION COMPLETE", flush=True)
    # apply
    st = load_state()
    res = st["results"]
    assert len(res) == len(preds), f"mismatch {len(res)} vs {len(preds)}"
    kept, removed = [], []
    counts = {}
    for idx, p in enumerate(preds):
        r = res[idx]
        cls = r["class"]
        if cls not in CLASSES:
            cls = "UNCLEAR"
        counts[cls] = counts.get(cls, 0) + 1
        if cls == "PREDICTION":
            newp = dict(p)
            newp["category"] = r["category"] if r["category"] in EXTRA_CATS else "other"
            if r["claim"] and r["claim"] != p["claim"]:
                newp["claim"] = r["claim"]
                newp["class_reviewed"] = "A"
            kept.append(newp)
        else:
            removed.append({
                "speaker": p["individual_name"],
                "claim": p["claim"],
                "date": p.get("date", ""),
                "source_url": p.get("source_url", ""),
                "class": cls,
                "reason": r.get("reason", "") or cls,
                "removed_at": "2026-10-02",
            })
    pool = json.load(open(POOL_FILE, encoding="utf-8"))
    pool.extend(removed)
    d["predictions"] = kept
    tmp = PRED_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PRED_FILE)
    pt = POOL_FILE.with_suffix(".tmp")
    pt.write_text(json.dumps(pool, indent=1, ensure_ascii=False), encoding="utf-8")
    pt.replace(POOL_FILE)
    st["stage"] = "A_applied"
    st["kept_counts"] = counts
    st["removed"] = len(removed)
    st["pool_size"] = len(pool)
    save_state(st)
    print(f"APPLIED: kept={len(kept)} removed={len(removed)} pool={len(pool)} counts={counts}", flush=True)


if __name__ == "__main__":
    main()
