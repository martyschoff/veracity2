# Competitive Landscape: SeerScore.AI vs existing work
(opus/high + web research, 2026-10-09)

## Closest equivalents found

1. **hayderi/forecasting-swarm** (GitHub)
   5-panelist multi-LLM prediction tool with Brier scoring ledger - calibrated
   probabilistic forecasting via independent model debate.
   vs SeerScore: closest structural cousin (multi-LLM panel + Brier). But it
   predicts EVENTS (forward-facing), doesn't track named pundits' track records,
   no harvest pipeline, no public grid, single debate round.

2. **lhl/realitycheck** (+ realitycheck-data knowledge base)
   Framework for rigorous systematic analysis of claims, sources, predictions,
   and argument chains. Claims tagged [F]actual/[T]heory/[H]ypothesis/[P]rediction.
   Active (v0.3.5 Jul 2026).
   vs SeerScore: does claim EXTRACTION and tagging well (similar to our gate),
   but is an analysis framework, not a tracker - no verdict resolution, no
   scoring, no per-person track records, no public grid.

3. **kachence/prediction-almanac**
   Self-updating awesome-list of predictions (daily bot refresh, active).
   vs SeerScore: aggregation/visibility only - no adjudication, no scoring.

4. **signal-tracker** (pip install, Reddit r/Python)
   Python prediction tracking framework.
   vs SeerScore: generic tracking, no LLM extraction, no panel/swarm.

5. **Established platforms** (not equivalent, but the landscape):
   - Metaculus: community forecasting + calibration, users ARE the forecasters
   - Good Judgment Open: Tetlock superforecasters, trained participants
   - PredictIt/Polymarket/Manifold: market-priced probabilities
   - PunditTracker (defunct ~2015): the only prior attempt at pundit
     accountability - manually tracked, died from labor intensity

## What nobody else does (our differentiation)

1. HARVEST FROM MEDIA: no project extracts pundit predictions from
   video/podcast transcripts at scale via LLM. PunditTracker died doing it
   manually; we automated it.
2. NAMED-PERSON TRACK RECORDS OVER YEARS: public grid of specific humans'
   calls, graded consistently, hover-able evidence.
3. MULTI-SOURCE ADJUDICATION: four differently-shaped judgment sources
   (swarm, agent-society, frontier single-judge, weighted panel) with
   disagreement logging for calibration.
4. OWN-VOICE EXTRACTION: strict no-quoted-material rule - guests' predictions
   are not attributed to the host.
5. Public, always-on, self-updating (twice-daily pipeline).

## What others have that we lack

- Calibration scoring depth (Brier decomposition, reliability diagrams) -
  hayderi/forecasting-swarm has a Brier ledger we could mimic
- Community/market resolution signals (Polymarket prices as ground truth)
- Claim-matching research tooling (kinit-sk/llms-claim-matching - matching
  claims across documents, useful for our same-claim dedup)
- Timestamped proof of prediction priority (OpenTimestamps integration)

## Gaps identified for our roadmap
1. Brier ledger per claim (multi-source probability) - aligns with the
   scoring work just shipped
2. Same-claim dedup across sources via claim-matching embeddings
3. OpenTimestamps for prediction-priority proof
4. Reliability diagrams per pundit (calibration curves) - once N grows
