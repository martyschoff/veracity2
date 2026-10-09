# Veracity2 Ops Assessment — P0/P1/P2 Prioritized Analysis

**Date:** 2026-10-09  
**Scope:** Reliability, Code Quality, Operational Gaps, Improvements

---

## P0 — FIX IMMEDIATELY (blocks production or causes data loss)

### 1. `log_disagreement` crashes on NoneType `mc_result`
**File:** `scripts/delphicursor_worker.py:305`  
**Symptom:** Worker crashes with `TypeError: argument of type 'NoneType' is not a container or iterable`  
**Why:** When a prediction hasn't run through Monte Carlo yet, `mc_result` is `None`. The code does `'RIGHT' in mc_result` which throws on None.  
**Fix:**
```python
mc_result = pred.get('mc_result') or ''  # <-- add `or ''`
```
**Effort:** 5 minutes

---

### 2. DelphiCursor agent workspace isolation broken
**File:** `scripts/delphicursor_worker.py`  
**Symptom:** Repeated `no_verdict_file` failures (44 entries in `delphicursor_failures.jsonl`)  
**Why:** The agent finishes in ~45s (exit code 0) but never writes `verdict.json`. The system prompt is written to `system_prompt.txt` but the Cursor agent ignores it—likely because the agent runs in a sandboxed context that doesn't see the workspace files, or the prompt construction is wrong.  
**Root cause:** The `CURSOR_CLI` path was also changed mid-run (log shows both `cursor.cmd` and `agent.cmd` variants). The prompt tells the agent to "read system_prompt.txt" but the agent has no reason to—nothing in the CLI invocation tells it that file matters.  
**Fix:** Either:
1. Pass the full system prompt inline via the CLI (check if `--system-prompt` or `-s` flag exists), or
2. Concatenate the instructions directly into the user prompt string instead of relying on a file read.

**Effort:** 30 minutes

---

### 3. No health monitoring for workers
**Symptom:** Workers die silently; manual `head` checks required to notice  
**Why:** `miro_worker.py`, `swarm_worker.py`, `delphicursor_worker.py` all run as `pythonw` (no console). If they crash, nothing notices. The scheduled task `veracity-miro-worker` relaunches only miro.  
**Fix:** Add a simple heartbeat: each worker writes a timestamp to `data/<worker>_heartbeat.txt` every loop. A single watchdog script (or scheduled task) checks all heartbeats every 5 min and sends a desktop notification/email if any is stale.  
**Effort:** 1–2 hours

---

### 4. 3080 pool ports disappear after reboot with no restart
**File:** `OPERATIONS.md:38-40`  
**Symptom:** After TJ1 reboots, ports 11437–11441 stay down. Monte Carlo runs silently skip those endpoints.  
**Why:** No systemd/Windows Service to restart the Ollama instances.  
**Fix:** Create a startup script on the 3080 box that launches all 8 Ollama instances on their respective ports. Run it via Windows Task Scheduler "At startup" trigger.  
**Effort:** 1 hour

---

### 5. Double-locking pattern in `monte_carlo.py` is confusing and fragile
**File:** `scripts/monte_carlo.py:160–183`  
**Symptom:** Code acquires `FileLock`, then calls `locked_data()` which acquires the same lock. Works because `filelock` is reentrant, but readers assume nested locks are held by *different* processes.  
**Why:** The pattern was copy-pasted without understanding that `locked_data()` already locks.  
**Fix:** Pick one: either use `filelock` directly everywhere and drop `locked_data()`, or use `locked_data()` exclusively. Don't mix.  
**Effort:** 30 minutes per script (×4 scripts)

---

## P1 — FIX SOON (causes reliability issues, tech debt, or security exposure)

### 6. MiroFish Graphiti embedding mismatch
**File:** `data/miro_worker.log` (Oct 8 errors)  
**Symptom:** `ValueError: zip() argument 2 is longer than argument 1` in `graphiti_core/nodes.py:590`  
**Why:** The `graphiti_core` package has a bug where the embedding batch size doesn't match the node count. This is a library bug.  
**Fix:** Pin a known-good version of `graphiti_core`, or patch the line locally:
```python
for node, name_embedding in zip(nodes, name_embeddings, strict=False):
```
**Effort:** 30 minutes (investigate version; patch if needed)

---

### 7. `panel_adjudicate.py` references undefined variables
**File:** `scripts/panel_adjudicate.py:64, 79`  
**Symptom:** Script crashes on `DATA` (undefined) and `NON_VOTERS` (undefined).  
**Why:** These were removed or never added; the script was never run successfully since the refactor.  
**Fix:** Add definitions:
```python
DATA = BASE / 'data' / 'predictions.json'
NON_VOTERS = {'Fact-Check', 'Twitter Bot', ...}  # define the set
```
Also add the `due()` function that's called but missing.  
**Effort:** 20 minutes

---

### 8. No backup/versioning of `predictions.json`
**Symptom:** A corrupt write or accidental delete loses everything.  
**Why:** Single JSON file with ~40k lines, no redundancy.  
**Fix:** Add a daily backup cron/task:
```powershell
Copy-Item data/predictions.json "data/backups/predictions_$(Get-Date -f yyyyMMdd).json"
```
Keep last 7 days. Also consider committing to a private git branch nightly.  
**Effort:** 20 minutes

---

### 9. Surge token hardcoded in `pipeline.py`
**File:** `src/pipeline.py:640`  
**Symptom:** Token `ea807c6f912951573c26c7fed2788f3f` is in source code.  
**Fix:** Move to `.env` file or environment variable; load via `os.getenv('SURGE_TOKEN')`.  
**Effort:** 10 minutes

---

### 10. Hardcoded absolute Windows paths everywhere
**Files:** Every script has `C:/Users/schof/...`  
**Why:** Breaks if you move the repo, run on another machine, or change username.  
**Fix:** Use relative paths from `Path(__file__).resolve().parent.parent` (already done in some files). Audit and fix all:
- `miro_worker.py:20` (`BASE = Path(r'C:/Users/schof/veracity2')`)
- `swarm_worker.py:10` (`LOCKF = r'C:/Users/schof/veracity2/...'`)
- `panel_adjudicate.py:16`
- `data_lock.py:18`

**Effort:** 1 hour

---

### 11. Duplicate code: `_deeplink()`, `condense()`, category colors
**Files:** `app.py`, `render.py`, `templates/index.html` (JS)  
**Why:** Three copies of the same logic. Changes require edits in 3 places.  
**Fix:** Factor into `src/utils.py`; import in app.py and render.py; for JS, render it server-side or expose via `/api/utils.js`.  
**Effort:** 1 hour

---

### 12. No CI/CD pipeline
**Symptom:** No automated tests run on commits; manual deploy only.  
**Fix:** Add `.github/workflows/ci.yml`:
```yaml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r requirements.txt
      - run: pytest tests/
```
**Effort:** 30 minutes

---

### 13. No retry/backoff on LLM endpoint failures
**File:** `src/pipeline.py:130–157`  
**Symptom:** If an endpoint is down, it's tried once and skipped. No tracking of which are unhealthy.  
**Fix:** Add exponential backoff + circuit breaker pattern. Track last-failure timestamp per endpoint; skip endpoints that failed in the last 5 min.  
**Effort:** 2 hours

---

### 14. Workers don't backoff on repeated failures
**Files:** All `*_worker.py`  
**Symptom:** If Neo4j is down, miro_worker retries every 60s forever, flooding logs.  
**Fix:** Exponential backoff: 60s → 2min → 5min → 10min cap. Reset on success.  
**Effort:** 30 minutes per worker

---

## P2 — IMPROVE WHEN TIME PERMITS (tech debt, quality, nice-to-haves)

### 15. Inconsistent file handle management
**Files:** Many scripts use `open()` without context managers.  
**Symptom:** File handles leak on exception; works but sloppy.  
**Fix:** Replace all `json.load(open(...))` with:
```python
with open(f, encoding='utf-8') as fh:
    data = json.load(fh)
```
**Effort:** 1 hour (audit all)

---

### 16. No type hints on most functions
**Files:** `miro_worker.py`, `swarm_worker.py`, `monte_carlo.py`, `render.py`  
**Fix:** Add `def foo(param: str) -> dict | None:` style hints. Run mypy.  
**Effort:** 2–3 hours

---

### 17. Logs grow unbounded
**Files:** `data/miro_worker.log` is 12k+ lines  
**Fix:** Use `logging.handlers.RotatingFileHandler` with 5MB max and 3 backups.  
**Effort:** 30 minutes

---

### 18. Consolidate workers into single supervisor
**Why:** 4 separate `pythonw` processes with separate lock files is fragile.  
**Fix:** One `supervisor.py` that spawns/monitors all workers as threads or subprocesses, handles heartbeats centrally.  
**Effort:** 4–6 hours

---

### 19. Replace JSON-field queues with proper job queue
**Why:** `mc_status`, `miro_status`, `delphicursor_status` fields in `predictions.json` are a poor man's job queue. Every write re-serializes the entire 40k-line file.  
**Fix:** Use SQLite `jobs` table or Redis. Keep `predictions.json` as the source of truth for prediction *data*, not job state.  
**Effort:** 8–12 hours (significant refactor)

---

### 20. Move config to a central file
**Why:** Endpoints, timeouts, paths scattered across 8+ scripts.  
**Fix:** Create `config.json` or `config.py`:
```json
{
  "llm_endpoints": [...],
  "paths": {"data": "data/predictions.json", ...},
  "timeouts": {"llm": 120, "hard": 300}
}
```
**Effort:** 2 hours

---

## Over-Engineered

1. **MiroFish (Graphiti/Neo4j agent-society simulation):** This is a 15-minute runtime per claim that adds marginal value over a simple LLM prompt. The graphiti_core library is buggy. Consider replacing with a single-shot LLM call like DelphiCursor.

2. **Monte Carlo 40-persona swarm:** 40 LLM calls per prediction when 5–10 would likely give statistically similar results. The diversity axes (region, politics) don't meaningfully affect LLM judgment.

3. **Panel weight tiers (1.5×/1.25×/1.0×):** Simulated panelists are all LLMs; weighting them differently is theater. Either use real human panelists with weights, or drop the weighting.

---

## Missing (Should Exist)

1. **Dead-letter queue:** Failed predictions go to `delphicursor_failures.jsonl` but there's no mechanism to retry them or surface them in the UI.

2. **Admin dashboard:** No way to see queue depths, worker health, endpoint status without reading log files.

3. **Idempotency keys:** Re-running a script can create duplicate predictions. Add `source_url + claim_hash` dedup.

4. **Rate limiting on API endpoints:** `/api/marty` has no auth or rate limiting.

5. **Tests for workers:** `tests/` has only model/store tests. No tests for monte_carlo, miro_worker, delphicursor_worker logic.

---

## Summary Table

| Priority | Issue | Effort |
|----------|-------|--------|
| P0 | `mc_result` NoneType crash | 5 min |
| P0 | DelphiCursor workspace isolation | 30 min |
| P0 | No worker health monitoring | 2 hr |
| P0 | 3080 pool no auto-restart | 1 hr |
| P0 | Double-locking pattern | 2 hr |
| P1 | Graphiti embedding bug | 30 min |
| P1 | panel_adjudicate undefined vars | 20 min |
| P1 | No predictions.json backup | 20 min |
| P1 | Hardcoded Surge token | 10 min |
| P1 | Hardcoded absolute paths | 1 hr |
| P1 | Duplicate code | 1 hr |
| P1 | No CI/CD | 30 min |
| P1 | No LLM retry/backoff | 2 hr |
| P1 | Workers don't backoff | 1.5 hr |
| P2 | File handle leaks | 1 hr |
| P2 | No type hints | 3 hr |
| P2 | Logs unbounded | 30 min |
| P2 | Consolidate workers | 6 hr |
| P2 | Proper job queue | 12 hr |
| P2 | Central config file | 2 hr |

**Total P0:** ~5.5 hours  
**Total P1:** ~8.5 hours  
**Total P2:** ~25 hours
