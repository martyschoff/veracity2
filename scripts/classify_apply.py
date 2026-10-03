"""Merge classify_state_{0,1,2}.json and apply classification to predictions.json."""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
PRED_FILE = DATA / "predictions.json"
POOL_FILE = DATA / "guest_pool.json"
STATE_FILE = DATA / "deep_qa_state.json"

VALID = ["PREDICTION", "PERSONAL", "SELF-REPORT", "PERSONAL-POSITION", "ADVICE", "PROMO", "UNCLEAR"]
CATS = {"ai", "finance", "geopolitics", "energy", "china", "ukraine", "health", "other"}


def main():
    d = json.load(open(PRED_FILE, encoding="utf-8"))
    preds = d["predictions"]
    nb = (len(preds) + 7) // 8
    merged = {}
    for k in range(3):
        st = json.load(open(DATA / f"classify_state_{k}.json", encoding="utf-8"))
        for b, out in st["results"].items():
            merged[int(b)] = out
    missing = [b for b in range(nb) if b not in merged]
    if missing:
        print(f"MISSING batches: {missing[:20]}... total {len(missing)}")
        sys.exit(1)
    kept, removed, counts = [], [], {}
    for idx, p in enumerate(preds):
        b, j = divmod(idx, 8)
        r = merged[b][str(j)]
        cls = r["class"]
        counts[cls] = counts.get(cls, 0) + 1
        if cls == "PREDICTION":
            newp = dict(p)
            newp["category"] = r["category"] if r["category"] in CATS else "other"
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
    prev = json.load(open(STATE_FILE, encoding="utf-8")) if STATE_FILE.exists() else {}
    prev.update({"stage": "A_applied", "kept_counts": counts, "removed": len(removed),
                 "pool_size": len(pool), "kept": len(kept)})
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(prev, indent=1), encoding="utf-8")
    tmp.replace(STATE_FILE)
    print(f"APPLIED kept={len(kept)} removed={len(removed)} pool={len(pool)} counts={counts}")
    per_person = {}
    for p in kept:
        per_person[p["individual_name"]] = per_person.get(p["individual_name"], 0) + 1
    print(json.dumps(per_person, indent=1))


if __name__ == "__main__":
    main()
