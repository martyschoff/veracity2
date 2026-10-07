# Seer Score — Manual Operations Guide

How to run the judgment pipeline by hand. All commands run from the repo root.

## The queues (data/predictions.json fields)

- `marty_verdict` — the owner's FINAL grade (correct/wrong). Independent of panels; panels never override it.
- `mc_status: queued` — Monte Carlo swarm queue (40 persona votes per prediction)
- `miro_status: queued` — MiroFish adjudication queue (Graphiti ingest → 2-round panel → verdict)

Grading in the app (http://127.0.0.1:8765, Right/Wrong buttons) auto-enqueues both.

## Manual swarm pass

```
python scripts/monte_carlo.py --n 40
```
Processes every `mc_status == queued` prediction: 40 diverse personas vote
(plausible/won't-happen + confidence), aggregated to `mc_result` like
`RIGHT (62% of 30 decided)`. Eligibility gate: predictions whose stated year
is still in the future are marked `not_due` and skipped (no premature verdicts).

Endpoints: nimo128 (Mac mini 32B) + upthread64 (llama3.1:8b — added 2026-10-06,
100% decisive in tests) + the 7×3080 pool (ports 11435-41, full
`/v1/chat/completions` paths required — call_llm posts to the URL verbatim).

## MiroFish worker (background service)

```
pythonw scripts/miro_worker.py   # silent loop, polls every 60s
```
Processes `miro_status == queued` one at a time: builds a claim fixture,
ensures Neo4j (laptop-local, tools/neo4j-community-5.26.0, JDK21) and the LLM
proxy (127.0.0.1:8899 — embeddings fixups) are up, runs
veracity-panel `scripts/run_claim_adjudication.py` via the backend venv,
writes `miro_result` + `miro_status: done`. Log: `data/miro_worker.log`.
Scheduled task `veracity-miro-worker` (every 5 min) relaunches it if dead.

## Pending marks ledger

Marks made while a sweep held a stale snapshot get wiped by that sweep's saves.
If that happens, grades live in `data/pending_marks.json`; apply with:

```
python scripts/apply_pending_marks.py
```

## Verdict sweep (weighted panel adjudication)

```
python scripts/panel_adjudicate.py --person "Ian Bremmer" [--year 2025] [--force]
```
3 weighted panelist votes per prediction (1.5×/1.25×/1.0× tiers), tally at
|score| >= 2.0. `--force` re-adjudicates predictions whose votes came back
all/mostly unclear (deadlocked runs). Persons-only sampling: fact-checkers and
publication accounts never vote. Skips not-yet-due predictions.

## Verdict precedence (display)

1. **Fact-Check** (pink bubble) — authoritative source confirms/refutes
   (elections, official outcomes). Panel models hallucinate post-cutoff facts.
2. **Marty's verdict** (amber) — final, independent.
3. **Panel** (green/ALMOST/TBD) — weighted votes.

## Locking

All writers of `data/predictions.json` share `data/predictions.json.lock`
(via `scripts/data_lock.py`): each writer re-reads the latest state under the
lock and overlays only its own changes. Never dump a stale in-memory snapshot.

## Deploy

```
python render.py   # bumps version +0.01 per pass
SURGE_TOKEN=<token> surge surge_dist/ veracity2.surge.sh
npx wrangler pages deploy surge_dist --project-name seerscore --branch main
```
Public mirrors: veracity2.surge.sh + seerscore.pages.dev.
