# Verdict Sweep Review: `scripts/panel_adjudicate.py`

**Reviewer:** Claude (automated analysis)  
**Date:** 2026-10-06  
**Scope:** Vote integrity, parallelism, judgment quality, observability, integration

---

## Summary

The verdict sweep (`panel_adjudicate.py`) is functional but has several architectural weaknesses that affect correctness, throughput, and reliability. The most critical issues are:

1. **Future-dated bias** — produces noisy "incorrect" verdicts for predictions not yet due
2. **Write race conditions** — concurrent runs with `miro_worker.py` and `monte_carlo.py` clobber `predictions.json`
3. **Single-threaded execution** — 4-GPU pool underutilized; a sweep of 100 predictions takes ~30+ minutes

Below is a prioritized list of improvements.

---

## P0 — Critical (Correctness / Data Integrity)

### P0.1: Add future-date guard to the adjudication prompt

**Problem:** The current prompt says "It is now late 2026. Judge ONLY whether the prediction has been proven correct, incorrect, or is not yet decidable by this date." This is too weak. Panelists still vote "incorrect" on predictions whose target date hasn't arrived, because the prompt doesn't explicitly instruct them that a *not-yet-due* prediction should be "unclear," not "incorrect."

The swarm (`monte_carlo.py`) already patched this with explicit language:

```python
"IMPORTANT: if the prediction's target date is still in the future, "
"it has NOT failed merely because it has not happened yet - answer 'yes' if current evidence "
"shows it is on track, 'unclear' if there is not enough evidence either way, and 'no' only if "
"there is positive evidence it failed or its deadline has passed unmet."
```

**Fix:** Inject the same guidance into `PROMPT`:

```python
PROMPT = """You are simulating panelist {name} ({role}) — weight {weight}x — on a predictions adjudication panel.

PREDICTION (made {date}): {claim}
TRANSCRIPT CONTEXT: {excerpt}

It is now late 2026. Judge ONLY whether the prediction has been proven correct, incorrect, or is not yet decidable.

CRITICAL: If the prediction's target date is still in the future, it has NOT failed merely because it hasn't happened yet. Answer:
- "correct" ONLY if there is positive evidence the predicted event occurred or is clearly on track
- "incorrect" ONLY if there is positive evidence it failed OR its deadline has passed unmet
- "unclear" if the deadline hasn't arrived and there isn't conclusive evidence either way

Answer STRICTLY as JSON: {{"vote": "correct"|"incorrect"|"unclear", "reasoning": "1-2 sentences"}}"""
```

**Why it matters:** Without this, correct predictions for future events (e.g., "2027 recession") get marked wrong, polluting accuracy stats.

**Effort:** Small (prompt change only)

---

### P0.2: Implement file locking to prevent `predictions.json` clobbering

**Problem:** Three scripts write to `predictions.json` concurrently:
- `panel_adjudicate.py` (this script)
- `miro_worker.py` (runs in a silent loop)
- `monte_carlo.py` (batch runs)

All three do `json.load → modify → json.dump` without locks. If `miro_worker.py` writes while a sweep is mid-run, the sweep's final save overwrites Miro verdicts (and vice versa).

**Fix:** Use `filelock` or OS-level locking:

```python
from filelock import FileLock

LOCK = BASE / 'data' / 'predictions.json.lock'

def load_and_lock():
    lock = FileLock(LOCK, timeout=60)
    lock.acquire()
    data = json.load(open(BASE / 'data' / 'predictions.json', encoding='utf-8'))
    return data, lock

def save_and_unlock(data, lock):
    json.dump(data, open(BASE / 'data' / 'predictions.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
    lock.release()
```

Apply the same pattern to `miro_worker.py` and `monte_carlo.py`.

**Alternatively:** Each process writes to a sidecar file (e.g., `panel_votes_{timestamp}.jsonl`) and a reconciler merges them periodically.

**Why it matters:** Without locking, verdicts from one process silently disappear when another overwrites the file.

**Effort:** Small-Medium (add `filelock` dep, update all three scripts)

---

### P0.3: Deduplicate votes before tallying

**Problem:** The current code appends new votes to `p['judgements']` without checking if the same panelist already voted:

```python
votes = list(p.get('judgements') or [])
for name in panelists:
    # ... no check for existing vote by this panelist
    votes.append({'panelist': f'{name} (simulated)', ...})
```

If the script crashes and restarts, the same panelist can vote multiple times on the same prediction, skewing the weighted score.

**Fix:** Deduplicate before appending:

```python
existing_panelists = {v['panelist'] for v in votes}
for name in panelists:
    label = f'{name} (simulated)'
    if label in existing_panelists:
        continue  # already voted
    # ... proceed with vote
```

**Why it matters:** Duplicate votes corrupt the weighted tally and can flip verdicts.

**Effort:** Small

---

### P0.4: Persist partial state after every vote (not every 5 predictions)

**Problem:** The script saves to disk only every 5 predictions:

```python
if (pi + 1) % 5 == 0:
    json.dump(d, ...)
```

If the process dies mid-prediction (e.g., timeout, OOM), up to 15 individual votes (3 panelists × 5 predictions) are lost.

**Fix:** Save after every prediction completes:

```python
if votes:  # at least one vote collected
    p['judgements'] = votes
    json.dump(d, open(...), ...)
```

Or use a write-ahead log (`.jsonl` sidecar) for votes, then batch-merge into `predictions.json` at the end.

**Why it matters:** A 2-hour sweep that crashes at minute 90 loses 30 minutes of work.

**Effort:** Small (change the save interval) or Medium (implement WAL)

---

## P1 — High (Performance / Reliability)

### P1.1: Parallelize votes across the 4-GPU pool

**Problem:** The script is single-threaded:

```python
for name in panelists:
    res = ask(POOL[port_i % 4], prompt)
```

With 3 panelists per prediction and 2-minute timeouts, each prediction takes up to 6 minutes sequentially. The 4 GPUs sit idle 75% of the time.

**Fix:** Use `concurrent.futures.ThreadPoolExecutor` (like `monte_carlo.py` does):

```python
import concurrent.futures

def vote_one(name, prompt, port):
    res = ask(port, prompt)
    if res is None:
        res = ask(NIMO, prompt)  # escalate
    return name, res

with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    futs = []
    for i, name in enumerate(panelists):
        prompt = PROMPT.format(...)
        futs.append(pool.submit(vote_one, name, prompt, POOL[i % 4]))
    for fut in concurrent.futures.as_completed(futs):
        name, res = fut.result()
        if res:
            votes.append({...})
```

**Expected speedup:** 3-4× (all panelists vote in parallel per prediction).

**Why it matters:** A sweep of 200 predictions drops from ~2 hours to ~30 minutes.

**Effort:** Medium

---

### P1.2: Add health checks and automatic failover for dead pool instances

**Problem:** Endpoints are hardcoded. If `11437` is down, every 4th vote hangs for 120 seconds (the curl timeout) before escalating to nimo.

```python
POOL = ['http://100.124.236.23:11435', 'http://100.124.236.23:11436',
        'http://100.124.236.23:11437', 'http://100.124.236.23:11438']
```

**Fix:**

1. **Health-check on startup:** Ping each endpoint with a tiny prompt; remove dead ones from the pool.
2. **Circuit breaker:** After 2 consecutive failures on an endpoint, mark it down for 5 minutes.

```python
def check_health(endpoint):
    try:
        r = subprocess.run(['curl', '-s', '-m', '5', f'{endpoint}/api/version'],
                           capture_output=True, timeout=10)
        return r.returncode == 0
    except:
        return False

POOL = [ep for ep in POOL if check_health(ep)]
if not POOL:
    raise RuntimeError("No healthy endpoints in pool")
```

**Why it matters:** One dead GPU shouldn't halve throughput.

**Effort:** Small-Medium

---

### P1.3: Use `httpx` instead of `subprocess` curl

**Problem:** Spawning `curl` via `subprocess.run` for every LLM call is inefficient and harder to debug. `pipeline.py` and `monte_carlo.py` already use `httpx` (via `call_llm`).

**Fix:** Replace the `ask()` function:

```python
import httpx

def ask(endpoint: str, prompt: str) -> dict | None:
    try:
        resp = httpx.post(
            f'{endpoint}/api/chat',
            json={'model': MODEL, 'stream': False, 'think': False,
                  'messages': [{'role': 'user', 'content': prompt}],
                  'options': {'num_predict': 300, 'num_ctx': 32768, 'temperature': 0.3}},
            timeout=120.0)
        resp.raise_for_status()
        c = resp.json()['message']['content']
        m = re.search(r'\{.*\}', c, re.S)
        return json.loads(m.group(0)) if m else None
    except Exception:
        return None
```

**Why it matters:** Cleaner code, better error messages, connection pooling for parallel requests.

**Effort:** Small

---

### P1.4: Add retry logic with exponential backoff

**Problem:** Currently, a failed vote escalates once to nimo, then gives up:

```python
res = ask(POOL[port_i % 4], prompt)
if res is None:
    res = ask(NIMO, prompt)
if res is None:
    continue  # vote lost
```

Transient network blips lose votes permanently.

**Fix:** Retry up to 3 times with backoff:

```python
import time

def ask_with_retry(endpoints: list, prompt: str, retries=3) -> dict | None:
    for attempt in range(retries):
        for ep in endpoints:
            res = ask(ep, prompt)
            if res:
                return res
        time.sleep(2 ** attempt)  # 1s, 2s, 4s
    return None
```

**Why it matters:** Network hiccups shouldn't permanently lose votes.

**Effort:** Small

---

## P2 — Medium (Judgment Quality / Observability)

### P2.1: Stratified panelist selection instead of pure random

**Problem:** `random.sample(pool_names, 3)` can repeatedly pick the same panelists across predictions, giving uneven coverage. It also doesn't ensure tier diversity (e.g., could pick 3 weight-1.0 commentators, missing the 1.5 professional forecasters).

**Fix:** Stratified sampling to guarantee at least one high-weight panelist when available:

```python
by_weight = {1.5: [], 1.25: [], 1.0: []}
for n in pool_names:
    by_weight.get(ind_w[n], by_weight[1.0]).append(n)

panelists = []
# 1 from highest tier available
for tier in [1.5, 1.25, 1.0]:
    if by_weight[tier]:
        panelists.append(random.choice(by_weight[tier]))
        break
# 2 more from the full pool (avoiding duplicates)
remaining = [n for n in pool_names if n not in panelists]
panelists.extend(random.sample(remaining, min(2, len(remaining))))
```

**Why it matters:** Ensures every prediction gets input from at least one expert-tier panelist, improving judgment quality.

**Effort:** Small

---

### P2.2: Track per-panelist accuracy for calibration

**Problem:** No mechanism tracks which simulated panelists are actually accurate. All panelists at the same weight tier are treated equally, even if one consistently votes wrong.

**Fix:** After verdicts are finalized (by human review or downstream systems), compute per-panelist accuracy:

```python
# In a separate calibration script:
calibration = {}  # panelist -> {correct: N, total: N}
for p in predictions:
    if p.get('verdict') not in ('correct', 'wrong'):
        continue
    for j in p.get('judgements', []):
        name = j['panelist']
        calibration.setdefault(name, {'correct': 0, 'total': 0})
        calibration[name]['total'] += 1
        if j['verdict'] == p['verdict']:
            calibration[name]['correct'] += 1
# Save to data/panelist_calibration.json
```

Future sweeps can then down-weight consistently inaccurate panelists or exclude them.

**Why it matters:** Enables iterative improvement of the panel's collective accuracy.

**Effort:** Medium (new calibration script + integration)

---

### P2.3: Add structured logging with per-run metrics

**Problem:** The current logging is minimal (`print()` statements). No structured logs for post-hoc analysis:

```python
print(f'{pi + 1}/{len(targets)} done | votes={len(votes)} score={round(score, 2)} verdict={p.get("verdict")}', flush=True)
```

**Fix:** Use Python `logging` with JSON output:

```python
import logging
import json

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[logging.FileHandler(BASE / 'data' / 'sweep_runs.jsonl')]
)
logger = logging.getLogger('panel_adjudicate')

def log_vote(pred_id, panelist, vote, weight, score, verdict):
    logger.info(json.dumps({
        'event': 'vote',
        'pred_id': pred_id,
        'panelist': panelist,
        'vote': vote,
        'weight': weight,
        'score': score,
        'verdict': verdict,
        'ts': datetime.now().isoformat()
    }))
```

**Why it matters:** Enables debugging, auditing, and per-run analytics (how many verdicts per run, average score, etc.).

**Effort:** Small

---

### P2.4: Skip predictions with `test_eligible_at` in the future

**Problem:** The script filters by `--person` and `--year` but doesn't respect `test_eligible_at`, which `monte_carlo.py` uses to skip not-yet-due predictions.

**Fix:** Add the same eligibility check:

```python
from datetime import date

today = date.today().isoformat()
targets = [p for p in d['predictions']
           if p['individual_name'] == args.person
           and not p.get('removed')
           and not p.get('gate_status')
           and (args.year is None or p.get('date', '').startswith(args.year))
           and (p.get('test_eligible_at') or '1900-01-01') <= today]
```

**Why it matters:** Prevents wasting votes on predictions that can't be judged yet.

**Effort:** Small

---

### P2.5: Add domain-aware prompt context

**Problem:** The prompt doesn't include the prediction's category or domain. A geopolitics prediction and an AI prediction get the same generic prompt.

**Fix:** Include category in the prompt:

```python
PROMPT = """You are simulating panelist {name} ({role}) — weight {weight}x — on a predictions adjudication panel.

DOMAIN: {category}
PREDICTION (made {date}): {claim}
TRANSCRIPT CONTEXT: {excerpt}
...
"""

# In the loop:
prompt = PROMPT.format(..., category=p.get('category', 'general'), ...)
```

**Why it matters:** Domain context helps the LLM apply relevant expertise.

**Effort:** Small

---

## P2.6: Integration with `miro_worker.py` and `monte_carlo.py`

**Current state:** All three scripts operate independently on `predictions.json`:
- `miro_worker.py` — continuous loop, processes `miro_status == 'queued'`
- `monte_carlo.py` — batch run, processes `mc_status == 'queued'`
- `panel_adjudicate.py` — manual run, processes by `--person`/`--year`

**Recommended integration pattern:**

1. **Shared file locking** (see P0.2) — all three use the same lock file.

2. **Status field coordination:**
   - Add `panel_status` field: `null` → `queued` → `in_progress` → `done`
   - The sweep sets `panel_status = 'in_progress'` when starting a prediction, preventing other processes from touching it.

3. **Pipeline orchestration:**
   ```
   [Extraction] → [Gating] → [Panel Sweep] → [MiroFish (optional)] → [Monte Carlo (optional)] → [Final Verdict]
   ```
   The verdict sweep should run *before* Monte Carlo (panel gives initial signal), or they should be chained:
   ```python
   # In panel_adjudicate.py, after setting verdict:
   if p.get('verdict') in ('correct', 'wrong') and p.get('mc_status') in (None, 'none'):
       p['mc_status'] = 'queued'  # trigger swarm validation
   ```

4. **Separate data stores (future):** Instead of one monolithic `predictions.json`, use:
   - `predictions.json` — canonical prediction records
   - `votes/panel_{pred_id}.json` — panel votes
   - `votes/miro_{pred_id}.json` — MiroFish results
   - `votes/mc_{pred_id}.json` — Monte Carlo results
   
   A reconciler merges them into final verdicts.

**Effort:** Large (architectural change)

---

## Summary Table

| ID | Issue | Impact | Effort |
|----|-------|--------|--------|
| P0.1 | Future-date bias in prompt | Correctness | Small |
| P0.2 | No file locking | Data loss | Small-Medium |
| P0.3 | Vote deduplication | Correctness | Small |
| P0.4 | Infrequent state saves | Data loss | Small |
| P1.1 | Single-threaded execution | 4× slower | Medium |
| P1.2 | No health checks for pool | Reliability | Small-Medium |
| P1.3 | subprocess curl | Maintainability | Small |
| P1.4 | No retry logic | Lost votes | Small |
| P2.1 | Random panelist selection | Quality | Small |
| P2.2 | No calibration tracking | Quality | Medium |
| P2.3 | Minimal logging | Observability | Small |
| P2.4 | Ignores `test_eligible_at` | Wasted work | Small |
| P2.5 | No domain context | Quality | Small |
| P2.6 | No integration with sibling scripts | Architecture | Large |

---

## Recommended Implementation Order

1. **Immediate (this week):**
   - P0.1 (future-date prompt fix)
   - P0.3 (vote deduplication)
   - P0.4 (save after every prediction)
   - P2.4 (respect `test_eligible_at`)

2. **Short-term (next 2 weeks):**
   - P0.2 (file locking across all scripts)
   - P1.3 (switch to httpx)
   - P1.4 (retry logic)
   - P2.3 (structured logging)

3. **Medium-term:**
   - P1.1 (parallelize votes)
   - P1.2 (health checks)
   - P2.1 (stratified selection)
   - P2.5 (domain context)

4. **Longer-term:**
   - P2.2 (calibration tracking)
   - P2.6 (integration architecture)
