"""Merge deepqa_judge_state_{0,1}.json and apply judge results to predictions.json.

Removals (REPORTED/QUOTED/PAST-FACT/NOT-FOUND) go to guest pool; OWNS/KEEP-REVISED
stay, with context_excerpt replacing thin transcript_excerpt and revised claims.
"""
import json
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
PRED_FILE = DATA / "predictions.json"
POOL_FILE = DATA / "guest_pool.json"
STATE_FILE = DATA / "deep_qa_state.json"

INVALID = {"REPORTED", "QUOTED", "PAST-FACT", "NOT-FOUND"}


def main():
    d = json.load(open(PRED_FILE, encoding="utf-8"))
    preds = d["predictions"]
    judged = {}
    for k in range(4):
        stf = DATA / f"deepqa_judge_state_{k}.json"
        if not stf.exists():
            print(f"MISSING state {stf}")
            return
        st = json.load(open(stf, encoding="utf-8"))
        judged.update(st.get("judged", {}))
    pending_skip = [p["id"] for p in preds if (judged.get(p["id"], {}).get("status") != "judged")]
    if pending_skip:
        print(f"WARNING: {len(pending_skip)} preds not fully judged; they will be skipped",
              json.dumps(pending_skip[:5]))
    kept, removed, counts = [], [], Counter()
    for p in preds:
        e = judged.get(p["id"], {})
        if e.get("status") != "judged":
            counts.setdefault("UNJUDGED-KEPT", 0)
            counts["UNJUDGED-KEPT"] += 1
            kept.append(p)
            continue
        origin = e.get("origin", "SKIP")
        counts[origin] += 1
        if origin in INVALID:
            removed.append({
                "speaker": p["individual_name"],
                "claim": p["claim"],
                "date": p.get("date", ""),
                "source_url": p.get("source_url", ""),
                "class": origin,
                "reason": (e.get("reason", "") or "")[:300],
                "removed_at": "2026-10-03",
            })
            continue
        newp = dict(p)
        ce = (e.get("context_excerpt") or "").strip()
        if len(ce) > len(p.get("transcript_excerpt") or ""):
            newp["transcript_excerpt"] = ce
        rc = (e.get("revised_claim") or "").strip()
        if rc:
            newp["claim"] = rc
        newp["deep_qa"] = e.get("origin", "")
        kept.append(newp)
    pool = json.load(open(POOL_FILE, encoding="utf-8"))
    pool.extend(removed)
    d["predictions"] = kept
    tmp = PRED_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PRED_FILE)
    pt = POOL_FILE.with_suffix(".tmp")
    pt.write_text(json.dumps(pool, indent=1, ensure_ascii=False), encoding="utf-8")
    pt.replace(POOL_FILE)
    prev = json.load(open(STATE_FILE, encoding="utf-8")) if STATE_FILE.exists() else {}
    prev.update({"stage": "B_applied", "counts": dict(counts), "removed": len(removed),
                 "pool_size": len(pool), "kept": len(kept)})
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(prev, indent=1), encoding="utf-8")
    tmp.replace(STATE_FILE)
    print(f"APPLIED kept={len(kept)} removed={len(removed)} pool={len(pool)}")
    print(dict(counts))
    per = Counter(p["individual_name"] for p in kept)
    print(json.dumps(per, indent=1))


if __name__ == "__main__":
    main()
