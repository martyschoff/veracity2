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

## 3. AI cross-panel voting (DESIGNED, awaiting go)
- Predictions in NON-ai categories that mention "AI"/"artificial intelligence"
  (word-boundary match, also "A.I.", "artificial-intelligence") get a SECOND
  vote source: the AI panel, at WEIGHT 0.5 per panelist.
- Votes consolidate across panels: 2 agreeing votes still decides, weighted
  (1.0 primary + 0.5 AI each; fact-checker weights unchanged).
- AI-category predictions themselves don't get a second AI vote.
- Case: Zeihan "China's AI program limited by chips" → geopolitics + AI panel.

## 4. QA process (STANDING RULE, implemented in pipeline)
- One model judges another model's output BEFORE the main agent sees it —
  applies to BOTH code and content. The agent reviews already-QA'd results
  only; rejects go back to the producing model (retry/escalate), not to Marty.
  - Verdicts: local QA judge reviews the judgement bundle before finalizing
    (qa_approve in src/pipeline.py); rejected verdicts go back for re-test.
  - Extraction/speaker-attribution results (nimo128 etc.) get the same
    treatment: results are judged by the local model; unsatisfactory output
    from one bot (nimo128) escalates to another (tower2).

## 2. Also held (previously agreed, awaiting go)
- Backfill completion check for Bremmer (GZERO) + Diamandis to 2024-04-30 (agent running)
- Verdict system display already live; cron 8am/8pm live
- TOMORROW: benchmark local model tok/s (user asked; needs idle server)
- LLM dedupe run results: review merged groups, then render+deploy+commit
