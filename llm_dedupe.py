# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""LLM-assisted dedupe: find restatements of the SAME prediction, even when
worded differently. Uses local Qwen model first, Mac Ollama fallback (same
endpoints as src/pipeline.py). Conservative: merges only clear same-claim groups.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from src.pipeline import call_llm

DATA = Path(__file__).parent / "data" / "predictions.json"
CHUNK = 55

SYSTEM = (
    "You are deduplicating prediction claims made by ONE person. "
    "Some claims are restatements of the SAME underlying prediction made at "
    "different times (possibly worded differently, numbers may drift slightly). "
    "Others are genuinely different predictions even if on the same topic. "
    "Group ONLY claims that assert the same underlying testable outcome. "
    "Return JSON: {\"groups\": [[i, j, ...], ...]} using the integer ids given. "
    "Singletons (claims that match nothing) must be omitted. Never invent ids. "
    "Be conservative: when unsure whether two claims are the same prediction, do NOT group them."
)


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def llm_cluster(claims):
    """claims: list of (idx, text). Returns list of index-groups."""
    groups = []
    for chunk in chunks(claims, CHUNK):
        lines = "\n".join(f"{idx}: {c[:220]}" for idx, c in chunk)
        raw = call_llm(SYSTEM, f"Claims:\n{lines}\n\nReturn the groups JSON now.", max_tokens=2500)
        if not raw:
            continue
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            continue
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        valid_ids = {idx for idx, _ in chunk}
        for g in parsed.get("groups", []):
            if isinstance(g, list) and len(g) >= 2 and all(x in valid_ids for x in g):
                groups.append([int(x) for x in g])
    return groups


def main(people=None):
    data = json.loads(DATA.read_text(encoding="utf-8"))
    preds = data["predictions"]
    by_person = {}
    for i, p in enumerate(preds):
        if people and p["individual_name"] not in people:
            continue
        if p.get("stated_count", 1) > 1:
            continue  # already canonical of a group
        by_person.setdefault(p["individual_name"], []).append(i)

    absorbed = set()
    merged = 0
    for person, idxs in by_person.items():
        claims = [(i, preds[i]["claim"]) for i in idxs]
        groups = llm_cluster(claims)
        print(f"{person}: {len(claims)} claims -> {len(groups)} groups")
        for g in groups:
            g = sorted(g, key=lambda i: preds[i]["date"])
            canon = preds[g[0]]
            occ = list(canon.get("occurrences", []))
            for idx in g[1:]:
                d = preds[idx]
                occ.append({"date": d["date"], "url": d.get("source_url", ""),
                            "claim": d["claim"], "id": d["id"]})
                absorbed.add(idx)
                merged += 1
            canon["occurrences"] = occ
            canon["stated_count"] = 1 + len(occ)

    data["predictions"] = [p for i, p in enumerate(preds) if i not in absorbed]
    DATA.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Absorbed {merged} restatements; {len(preds)} -> {len(data['predictions'])}")


if __name__ == "__main__":
    main(sys.argv[1:] or None)
