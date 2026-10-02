# Pending UI/Data Changes — awaiting go command

## 0. Panel/predictor rule (USER RULE, must implement in verdict logic)
- A predictor can sit on panels, but CANNOT panel-vote on their own predictions.
- Predictors: Zeihan, Doomberg, Diamandis, Bremmer + one more shortly.
- In the testing stage: when judging a prediction authored by X, exclude any
  judgement from panelist X.

## 1. Dedupe / condense duplicate predictions per individual (DESIGNED, not built)

**Matching:**
- Normalize: lowercase, strip punctuation, remove filler ("will", "going to", "likely")
- Two-stage: key-entity + number match, then fuzzy token overlap (Jaccard ~0.75 threshold)
- LLM arbitrates borderline pairs only
- NOT duplicates: same wording but drifted numbers ("20% decline" vs "30% decline") — separate claims
- Restatements across time ARE duplicates of one claim (conviction over time), earliest date = true prediction date

**Condensed block:**
> **"Democrats sweep the midterms"** — stated 14x (Sep 2025 - Oct 2026)
> first: [url] | latest: [url] | +12 more sources
- "x14" chip VISIBLE ON THE CARD (user decision)
- All 14 dates + URLs preserved behind expandable / detail overlay
- ONE verdict per merged block; all occurrences inherit it (user decision)

**Effect:** Zeihan's 246 preds likely collapse to 40-80 distinct blocks; testing pipeline judges distinct claims only.

## 2. Also held (previously agreed, awaiting go)
- Backfill completion check for Bremmer (GZERO) + Diamandis to 2024-04-30 (agent running)
- Verdict system display already live; cron 8am/8pm live
- TOMORROW: benchmark local model tok/s (user asked; needs idle server)
- LLM dedupe run results: review merged groups, then render+deploy+commit
