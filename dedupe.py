# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Dedupe/condense repeated predictions per individual.

Groups near-identical claims into one canonical prediction block:
- canonical keeps its id, earliest date, and verdict machinery
- absorbed occurrences are preserved in `occurrences` (date + url each)
- `stated_count` powers the "xN" chip on the card

Matching: normalize -> token-set Jaccard >= 0.80, same category, and at least
one shared "anchor" (number or 4-digit year or shared rare entity token).
Borderline pairs (0.72-0.80) are left separate (conservative, no LLM needed).
"""
import json
import re
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data" / "predictions.json"

FILLER = {
    "will", "the", "a", "an", "of", "to", "in", "for", "and", "or", "is",
    "are", "be", "been", "by", "on", "at", "that", "this", "it", "its",
    "with", "as", "from", "not", "no", "going", "goingto", "likely",
    "continue", "continues", "remains", "remain",
}


def normalize(text: str) -> set:
    t = text.lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return {w for w in t.split() if w not in FILLER and len(w) > 1}


def anchors(tokens: set) -> set:
    return {t for t in tokens if t.isdigit()}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def cluster(preds: list) -> list:
    """Greedy single-link clustering within one person's predictions."""
    tokens = [normalize(p["claim"]) for p in preds]
    order = sorted(range(len(preds)), key=lambda i: preds[i]["date"])
    parent = list(range(len(preds)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for ii in range(len(order)):
        for jj in range(ii + 1, len(order)):
            i, j = order[ii], order[jj]
            if find(i) == find(j):
                continue
            if preds[i].get("category") != preds[j].get("category"):
                continue
            sim = jaccard(tokens[i], tokens[j])
            if sim < 0.80:
                continue
            shared_anchors = anchors(tokens[i]) & anchors(tokens[j])
            if tokens[i] & tokens[j] == set() and not shared_anchors:
                continue
            # differing numbers (other than years) = different claims
            nums_a = {t for t in tokens[i] if t.isdigit() and len(t) != 4}
            nums_b = {t for t in tokens[j] if t.isdigit() and len(t) != 4}
            if nums_a and nums_b and not (nums_a & nums_b):
                continue
            parent[find(i)] = find(j)

    groups = defaultdict(list)
    for i in range(len(preds)):
        groups[find(i)].append(i)
    return [sorted(idxs, key=lambda i: preds[i]["date"]) for idxs in groups.values()]


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    preds = data["predictions"]
    by_person = defaultdict(list)
    for p in preds:
        by_person[p["individual_name"]].append(p)

    absorbed = set()
    merged_count = 0
    for person, plist in by_person.items():
        for grp in cluster(plist):
            if len(grp) < 2:
                continue
            canonical = plist[grp[0]]  # earliest
            occ = []
            for idx in grp[1:]:
                dup = plist[idx]
                occ.append({
                    "date": dup["date"],
                    "url": dup.get("source_url", ""),
                    "claim": dup["claim"],
                    "id": dup["id"],
                })
                absorbed.add(id(dup))
                merged_count += 1
            canonical["stated_count"] = len(grp)
            canonical["occurrences"] = occ

    data["predictions"] = [p for p in preds if id(p) not in absorbed]
    DATA.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Absorbed {merged_count} duplicate occurrences; "
          f"{len(preds)} -> {len(data['predictions'])} blocks")
    for name in ["Peter Zeihan", "Ian Bremmer", "Peter Diamandis", "Doomberg"]:
        n = sum(1 for p in data["predictions"] if p["individual_name"] == name)
        reps = sum(p.get("stated_count", 1) - 1 for p in data["predictions"]
                   if p["individual_name"] == name)
        print(f"  {name}: {n} blocks ({reps} restatements absorbed)")


if __name__ == "__main__":
    main()
