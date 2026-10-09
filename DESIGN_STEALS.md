# Design: Competitive Feature Integration
**Date:** 2026-10-09  
**Status:** Design (no implementation)  
**Sources:** COMPETITIVE_LANDSCAPE.md analysis of hayderi/forecasting-swarm, kinit-sk/llms-claim-matching, Polymarket, OpenTimestamps

---

## Overview

Four features identified from the competitive landscape that would strengthen SeerScore.AI's differentiation. This document covers the HOW of integration—data structures, component interactions, and API surfaces—without implementation.

---

## 1. Brier Ledger & Calibration Scoring Depth

**Source:** hayderi/forecasting-swarm's Brier scoring ledger  
**Gap addressed:** We score verdicts but don't track probability calibration over time

### 1.1 Design Goals

- Track per-source probability estimates (Monte Carlo consensus %, panel confidence, market price) at verdict time
- Compute Brier scores per prediction: `(probability - outcome)²`
- Generate reliability diagrams (calibration curves) per pundit once N ≥ 20 predictions resolved

### 1.2 Data Model Extension

Add to each prediction in `predictions.json`:

```json
{
  "id": "existing-uuid",
  "claim": "...",
  "brier_ledger": {
    "recorded_at": "2026-10-09T12:00:00Z",
    "probabilities": {
      "monte_carlo": 0.72,
      "miro": 0.68,
      "delphicursor": 0.75,
      "panel_weighted": 0.71,
      "polymarket": 0.65
    },
    "resolved_outcome": 1,
    "brier_scores": {
      "monte_carlo": 0.0784,
      "miro": 0.1024,
      "delphicursor": 0.0625,
      "panel_weighted": 0.0841,
      "polymarket": 0.1225
    }
  }
}
```

### 1.3 New Module: `src/brier.py`

**Responsibilities:**
- `record_probabilities(pred_id, source_probs: dict)` — called when adjudication completes
- `compute_brier(prob: float, outcome: int) -> float` — simple `(p - o)²`
- `finalize_brier(pred_id, outcome: int)` — computes scores for all recorded probabilities
- `get_calibration_data(pundit: str) -> list[tuple[prob, outcome]]` — aggregates for diagrams

**Integration points:**
- `monte_carlo.py` — after consensus calculation, call `record_probabilities()` with MC result
- `panel_adjudicate.py` — after panel vote, add panel probability
- Final verdict writer — calls `finalize_brier()` when outcome is known

### 1.4 Aggregation: Per-Pundit Reliability

New file: `data/calibration/<pundit_slug>.json`

```json
{
  "pundit": "Peter Zeihan",
  "pundit_slug": "peter-zeihan",
  "total_resolved": 47,
  "mean_brier": 0.182,
  "calibration_buckets": {
    "0.0-0.1": {"count": 3, "actual_rate": 0.00},
    "0.1-0.2": {"count": 5, "actual_rate": 0.20},
    "0.2-0.3": {"count": 8, "actual_rate": 0.25},
    ...
    "0.9-1.0": {"count": 6, "actual_rate": 0.83}
  }
}
```

**Reliability diagram generation:**  
- Render via `matplotlib` or client-side JS (D3/Chart.js)
- X-axis: predicted probability bucket  
- Y-axis: actual outcome rate  
- Perfect calibration = diagonal line

### 1.5 UI Surface

- **Pundit card:** Add "Calibration" tab showing reliability diagram + mean Brier
- **Prediction detail:** Show `brier_ledger` with source probability breakdown
- **Leaderboard:** Sort by mean Brier (lower = better calibrated)

### 1.6 Migration Path

Existing predictions without `brier_ledger`:
- Backfill from `mc_result`, `miro_result`, `delphicursor_result` where available
- Mark as `"backfilled": true` to distinguish from native recordings

---

## 2. Market Resolution Signals (Polymarket Integration)

**Source:** Polymarket/Manifold price as ground truth proxy  
**Gap addressed:** Resolution depends entirely on our LLM adjudication—no external anchor

### 2.1 Design Goals

- Match our claims to active Polymarket markets where applicable
- Use market price as one signal in adjudication (not sole determinant)
- Use market resolution as ground truth when market resolves

### 2.2 Claim-to-Market Matching

New module: `src/market_matcher.py`

**Flow:**
1. On harvest, embed claim text using same embedder as claim-matching (§3)
2. Query Polymarket API for active markets (they have ~2000 at any time)
3. Embed market question text
4. Cosine similarity match; threshold ≥ 0.85 for candidate match
5. Human review queue for ambiguous matches (0.75–0.85 similarity)

**Data model addition:**

```json
{
  "market_link": {
    "platform": "polymarket",
    "market_id": "0x1234...",
    "market_question": "Will Russia control Kharkiv by Dec 2026?",
    "match_confidence": 0.92,
    "match_method": "embedding_auto",
    "linked_at": "2026-10-09T14:00:00Z"
  }
}
```

### 2.3 Price Polling

New scheduled task: `market_price_worker.py`

**Cadence:** Every 6 hours for linked predictions  
**Data stored:**

```json
{
  "market_prices": [
    {"ts": "2026-10-09T00:00:00Z", "price": 0.62},
    {"ts": "2026-10-09T06:00:00Z", "price": 0.65},
    {"ts": "2026-10-09T12:00:00Z", "price": 0.67}
  ]
}
```

### 2.4 Integration into Adjudication

Modify `panel_adjudicate.py` weighting:

| Source | Current Weight | With Market |
|--------|---------------|-------------|
| Monte Carlo consensus | 1.0 | 0.8 |
| MiroFish verdict | 1.0 | 0.8 |
| DelphiCursor verdict | 1.0 | 0.8 |
| **Polymarket price** | N/A | 1.2 |

Market signal only included if:
- `match_confidence ≥ 0.90`
- Market has ≥ $50k volume (liquidity threshold)
- Price history shows ≥ 3 data points (not flash-created)

### 2.5 Market Resolution as Ground Truth

When Polymarket resolves a linked market:
- Automatically mark our prediction as resolved
- Set `resolved_outcome` from market resolution
- Flag as `"resolution_source": "polymarket"`
- Compute Brier scores

**Edge case:** Market resolves opposite to our LLM consensus  
- Log to `data/market_conflicts.jsonl` for review
- Don't auto-override; flag for manual review

### 2.6 API & UI

- `GET /api/prediction/{id}/market` — returns market link + price history
- Prediction card: show Polymarket price badge if linked
- Sparkline of price history in prediction detail view

---

## 3. Claim-Matching Embeddings (Same-Claim Dedup)

**Source:** kinit-sk/llms-claim-matching  
**Gap addressed:** Same prediction harvested from multiple sources creates duplicates

### 3.1 Design Goals

- Detect when two harvested claims express the same prediction
- Merge duplicates into canonical prediction with multiple sources
- Enable "this claim also made by" cross-referencing

### 3.2 Embedding Pipeline

New module: `src/claim_embeddings.py`

**Embedder choice:** `text-embedding-3-large` (OpenAI) or local `nomic-embed-text` via Ollama

**Embedding stored:**

```json
{
  "claim_embedding": {
    "model": "text-embedding-3-large",
    "vector": [0.012, -0.034, ...],  // 3072 dims, stored in separate file
    "embedded_at": "2026-10-09T10:00:00Z"
  }
}
```

**Vector storage:** Separate from `predictions.json` to avoid bloat

- `data/embeddings/claims.npy` — numpy array, shape (N, 3072)
- `data/embeddings/claim_index.json` — maps prediction_id to array row

### 3.3 Dedup Flow

On harvest of new prediction:

```
1. Embed new claim text
2. Load claim vectors for same pundit (narrow search)
3. Compute cosine similarity against all
4. If max_similarity ≥ 0.92:
   → Flag as potential duplicate
   → Add to review queue OR auto-merge if ≥ 0.97
5. If 0.85 ≤ similarity < 0.92:
   → Flag as "related claim" for linking
```

### 3.4 Merge Behavior

When claims are confirmed duplicates:

```json
{
  "id": "canonical-uuid",
  "claim": "The Fed will cut rates by September 2026",
  "sources": [
    {
      "source_id": "original-uuid",
      "harvested_from": "All-In Podcast E187",
      "harvested_at": "2026-08-15T...",
      "verbatim": "I think the Fed cuts before September"
    },
    {
      "source_id": "dupe-uuid",
      "harvested_from": "Chamath Twitter Space",
      "harvested_at": "2026-08-20T...",
      "verbatim": "Fed's gonna cut by September, mark my words"
    }
  ],
  "merged_at": "2026-10-09T...",
  "primary_source": "original-uuid"
}
```

### 3.5 Review Queue

New file: `data/dedup_queue.jsonl`

```json
{"pred_a": "uuid1", "pred_b": "uuid2", "similarity": 0.94, "queued_at": "...", "status": "pending"}
```

Admin UI endpoint: `GET /admin/dedup-queue`  
Actions: "Merge", "Not duplicate", "Link as related"

### 3.6 Integration Points

- `pipeline.py:extract_predictions()` — embed immediately after extraction
- New `dedup_worker.py` — batch process for existing predictions
- `render.py` — show "Also stated in: ..." links on merged predictions

### 3.7 Performance Considerations

- ~5000 predictions × 3072 dims = ~60MB for full vector store
- Use FAISS or Annoy for fast approximate nearest neighbor if N grows
- Initial implementation: brute-force cosine on filtered set (same pundit) is fast enough

---

## 4. OpenTimestamps for Prediction Priority Proof

**Source:** OpenTimestamps (Bitcoin-anchored timestamping)  
**Gap addressed:** No cryptographic proof of when we recorded a prediction

### 4.1 Design Goals

- Prove prediction was recorded before outcome was known
- Enable third-party verification without trusting our database
- Prevent retroactive claim manipulation

### 4.2 What Gets Timestamped

Hash of canonical prediction record:

```json
{
  "pundit": "Peter Zeihan",
  "claim": "Russia will face equipment shortages by Q3 2026",
  "harvested_at": "2026-06-15T10:30:00Z",
  "source_url": "https://youtube.com/watch?v=...",
  "verbatim_quote": "..."
}
```

**Hash function:** SHA-256 of JSON (keys sorted, no whitespace)

### 4.3 Timestamping Flow

New module: `src/timestamps.py`

```
1. On prediction finalization (after harvest gate passes):
   a. Canonicalize prediction JSON
   b. Compute SHA-256 hash
   c. Submit to OpenTimestamps calendar servers
   d. Receive .ots proof file (initially incomplete)
   
2. Background worker polls for Bitcoin confirmation:
   a. OTS proofs upgrade once anchored in Bitcoin block
   b. Store upgraded proof
   
3. On verification request:
   a. Return .ots file
   b. Verifier can check against any Bitcoin node
```

### 4.4 Data Model Addition

```json
{
  "timestamp_proof": {
    "hash": "a1b2c3d4...",
    "hash_input_version": 1,
    "ots_file": "data/timestamps/a1b2c3d4.ots",
    "submitted_at": "2026-10-09T10:00:00Z",
    "bitcoin_block": 892451,
    "bitcoin_merkle_root": "...",
    "confirmed_at": "2026-10-09T14:30:00Z",
    "status": "confirmed"
  }
}
```

### 4.5 Storage

- `data/timestamps/<hash>.ots` — binary OTS proof files
- `data/timestamps/pending.json` — list of hashes awaiting confirmation

### 4.6 New Worker: `timestamp_worker.py`

**Responsibilities:**
- Submit new predictions to OTS (batch, max 100/day free tier)
- Poll pending proofs for Bitcoin confirmation
- Update prediction records when confirmed

**Cadence:** Every 2 hours

### 4.7 Verification API

`GET /api/prediction/{id}/timestamp`

Response:
```json
{
  "prediction_id": "uuid",
  "hash": "a1b2c3d4...",
  "bitcoin_block": 892451,
  "block_timestamp": "2026-10-09T14:22:00Z",
  "verification_url": "https://opentimestamps.org/verify?hash=a1b2c3d4",
  "ots_download": "/api/prediction/{id}/timestamp.ots"
}
```

### 4.8 UI Surface

- Prediction card: "⛓️ Timestamped" badge with Bitcoin block number
- Hover/click: shows verification details + download link
- Trust signal: "This prediction was cryptographically recorded before the outcome"

### 4.9 Edge Cases

**Late harvests:** Predictions harvested after the source was published  
- Timestamp proves when *we* recorded it, not when pundit said it
- Source video/podcast timestamp is separate evidence
- Consider: also timestamp source URL + publication date

**Hash input changes:** If we change what fields are hashed  
- Version the hash input schema (`hash_input_version: 1`)
- Old proofs remain valid for their version
- Document canonical format per version

---

## Integration Summary

| Feature | New Files | Touches Existing | New Workers | Data Growth |
|---------|-----------|------------------|-------------|-------------|
| Brier Ledger | `src/brier.py` | `monte_carlo.py`, `panel_adjudicate.py`, `app.py` | None (inline) | ~200 bytes/pred |
| Market Signals | `src/market_matcher.py` | `panel_adjudicate.py`, `render.py` | `market_price_worker.py` | ~500 bytes/pred (if linked) |
| Claim Dedup | `src/claim_embeddings.py` | `pipeline.py`, `render.py` | `dedup_worker.py` | ~12KB/pred (embeddings) |
| OpenTimestamps | `src/timestamps.py` | `pipeline.py`, `app.py` | `timestamp_worker.py` | ~2KB/pred (.ots file) |

---

## Dependency on P0/P1 Fixes

These designs assume the following from REVIEW_OPS_ASSESSMENT.md are resolved:

| Design | Depends On |
|--------|------------|
| Brier Ledger | P1 §7 (panel_adjudicate.py must work) |
| Market Signals | P1 §13 (retry/backoff for external API calls) |
| Claim Dedup | P0 §2 (DelphiCursor must work for testing) |
| OpenTimestamps | P1 §8 (backup strategy—OTS is append-only) |

---

## Phasing Recommendation

1. **Phase 1:** Brier Ledger (lowest effort, highest immediate value for calibration story)
2. **Phase 2:** Claim Dedup (reduces noise in existing data, improves data quality)
3. **Phase 3:** OpenTimestamps (trust/verification story, low urgency)
4. **Phase 4:** Market Signals (requires external API, matching complexity)

---

## Open Questions

1. **Brier:** Should we weight Brier by claim importance/stakes, or treat all predictions equally?
2. **Markets:** What's our policy when market resolves opposite to LLM consensus?
3. **Dedup:** Auto-merge threshold 0.97—too aggressive? Need human review for all?
4. **OTS:** Pay for OTS calendar priority, or accept free-tier delays (hours to days)?
