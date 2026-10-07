# DelphiCursor — Design v2 (Critique & Improvements)

**Status:** DESIGN ONLY. Nothing implemented. Awaiting owner approval.

This document critiques the original `DELPHICURSOR_DESIGN.md` and proposes
improvements across five focus areas.

---

## 1. Decision Rule: WHEN Should DelphiCursor Run?

### Original Design
> "Reserved for high-stakes or Marty-contested predictions (e.g. run
> DelphiCursor only when Marty and the panel disagree)."

### Critique

The "Marty vs panel disagreement" trigger has several problems:

1. **Too narrow**: Many interesting claims never get a Marty mark (owner can't
   grade everything). Limiting to disagreements means DelphiCursor only runs
   on the subset the owner already reviewed — selecting for attention bias.

2. **Circular dependency**: If Marty's verdict is FINAL and independent anyway,
   what does DelphiCursor add on disputed claims? It can't override Marty, so
   it just... confirms or disagrees decoratively?

3. **Missing the real use case**: The value of a frontier model is **breaking
   ties and resolving edge cases** where lower-tier adjudicators failed — not
   re-litigating what Marty already decided.

4. **No consideration of contestedness signal**: A 51-49 Swarm split or a
   panel score of exactly 0.0 is genuinely contested and would benefit from
   escalation. A unanimous 40-0 Swarm vote doesn't need Opus to confirm.

5. **Category/domain blindness**: Some domains (AI capabilities, recent
   geopolitics) benefit more from Opus's live knowledge than others (energy
   markets with commodity prices). The trigger should weight domain.

### Improved Design

**Multi-factor escalation trigger** (any 2+ factors → eligible for DelphiCursor):

| Factor | Condition | Rationale |
|--------|-----------|-----------|
| **Vote margin** | Swarm split ≤ 30% (e.g. 35-65 or tighter) | Genuine disagreement |
| **Panel deadlock** | Panel score in [-1.5, +1.5] (no verdict threshold hit) | Weighted votes inconclusive |
| **Delphi3080 "unclear"** | `miro_result.verdict` contains "unclear" or confidence < 60% | Heavy machinery couldn't decide |
| **Recency-sensitive** | Prediction references events after 2024-01-01 | Opus has live knowledge; 32B has cutoff |
| **High-value predictor** | `panel_weight >= 1.25` on the individual | Track-record matters more |
| **Explicit escalation** | Owner sets `delphicursor_status: queued` manually | Human override |

**Exclusions** (never queue):
- Predictions with `verdict_source: authoritative` (fact-checked)
- Predictions with `marty_verdict` set (owner already decided — unless explicit override)
- Predictions not yet due (`test_eligible_at > today`)

**Daily cap**: Max 10 claims/day (budget control), prioritized by:
1. Explicit owner queue
2. Deadlock severity (smallest margin first)
3. Oldest unresolved first

### Open Questions for Owner
- Should Marty-marked predictions ever be eligible? (E.g., owner marks
  "tentative" and wants Opus second opinion?)
- Is `panel_weight >= 1.25` the right high-value threshold?
- Should category be a factor? (AI/geopolitics → more value from live model?)

---

## 2. Prompt/Contract Weaknesses

### Original Design
> "Same JSON schema as the panel (`{vote, reasoning}`) plus `confidence` and
> `sources_considered` field."

### Critique

1. **Sycophancy risk**: If the prompt includes `marty_note` or any hint of the
   owner's position, Opus will anchor to it. The panel prompt in
   `panel_adjudicate.py` already has this problem: it says "Marty marked: ..."
   in the fixture notes.

2. **Recency bias**: Opus trained on recent data will over-weight recent news
   over base rates. A prediction "oil will hit $200 by 2027" gets judged
   differently in a week with headlines vs. a quiet week.

3. **Overconfidence on uncertain claims**: Frontier models rarely say "I don't
   know." The 3-way `correct|incorrect|unclear` forces a judgment, but Opus
   will pick a side with false certainty.

4. **Missing adversarial structure**: One-shot prompts invite motivated
   reasoning. A single Opus call produces *a* judgment, not *the* judgment.

5. **No grounding in prediction semantics**: The prompt needs to define what
   "correct" means for future-dated predictions (is "on track" correct? what
   evidence standard?).

6. **Hallucination risk on public facts**: Even Opus hallucinates. For
   verifiable facts, it should be instructed to cite sources and admit
   uncertainty if it can't verify.

### Improved Design

**Fixture schema** (written to temp file, passed to agent):

```json
{
  "claim_id": "pred_xxx",
  "statement": "<the prediction text>",
  "made_by": "<individual name>",
  "made_on": "<date>",
  "category": "<ai|finance|geopolitics|...>",
  "time_horizon": "<target year or 'next-12-months'>",
  "transcript_excerpt": "<supporting quote, max 800 chars>",
  "source_url": "<link to original>",
  
  "adjudication_context": {
    "swarm_result": "RIGHT (62% of 38) | WRONG (71% of 40) | undetermined",
    "panel_score": 1.25,
    "panel_votes_summary": "2 correct, 1 unclear",
    "delphi3080_verdict": "unclear (confidence 45%)",
    "delphi3080_rationale": "<first 200 chars of miro_result.summary>"
  },
  
  "DO_NOT_INCLUDE": {
    "marty_verdict": "REDACTED — owner opinion must not influence judgment",
    "marty_note": "REDACTED"
  }
}
```

**Key fixture rules**:
- **Marty's position is NEVER in the fixture.** The agent must judge blind.
- Prior adjudicator results ARE included (they're evidence of contestedness,
  not authoritative signals).
- Source URL included so agent can optionally browse.

**Prompt template** (system message):

```
You are an impartial adjudicator for a predictions-vs-reality tracker.

TASK: Judge whether the attached prediction has been proven CORRECT, INCORRECT,
or remains UNCLEAR as of today ({current_date}).

DEFINITIONS:
- CORRECT: The predicted event happened, OR for future-dated predictions,
  current evidence strongly indicates it is on track to happen.
- INCORRECT: The predicted event failed, its deadline passed unmet, OR current
  evidence strongly indicates it will not happen.
- UNCLEAR: Insufficient evidence exists to judge either way. Use this if you
  are genuinely uncertain — do not guess.

RULES:
1. You are judging the PREDICTION, not the predictor. Prior adjudicators
   disagreed — your job is to break the tie with superior reasoning.
2. For claims about verifiable public facts, you may browse to confirm. Cite
   your source if you do.
3. Do NOT default to "unclear" out of excessive caution. If you have a
   defensible position, commit to it.
4. Do NOT default to "correct" or "incorrect" out of false confidence. If the
   evidence is ambiguous, say UNCLEAR.
5. Predictions about the future that haven't happened yet are NOT automatically
   unclear — judge whether they are ON TRACK or OFF TRACK based on current
   evidence.
6. Confidence should reflect YOUR epistemic state, not the prediction's
   boldness.

OUTPUT: Write a JSON file to data/delphicursor_verdicts/{claim_id}.json:
{
  "vote": "correct" | "incorrect" | "unclear",
  "confidence": 0-100,
  "reasoning": "2-3 sentences explaining your judgment",
  "sources_checked": ["url1", "url2"] or [],
  "dissent_from_prior": "Why you disagree with swarm/panel/delphi3080, if you do"
}
```

**Guardrails against failure modes**:

| Failure Mode | Guardrail |
|--------------|-----------|
| Sycophancy | Marty position redacted from fixture |
| Overconfidence | Explicit "do not guess" instruction + confidence field |
| Recency bias | Instruction to judge trajectory, not headlines |
| Hallucination | Instruction to cite sources; optional browse |
| Anchoring to prior adjudicators | Include priors as "evidence of dispute", not authority |

**Post-hoc calibration check** (not in prompt, in worker logic):
- If Opus returns confidence > 90% but disagrees with 3+ prior adjudicators,
  flag for manual review.
- If Opus returns "unclear" on something Swarm was 90%+ decisive on, flag.

### Open Questions for Owner
- Should the agent be allowed to browse the source URL? (Adds latency, may
  find different evidence than the excerpt.)
- Should transcript_excerpt be longer (full context) or shorter (focus)?
- Should there be a "refuse to judge" option for malformed claims?
- Should confidence calibration warnings go to owner, or just be logged?

---

## 3. Cost/Budget Controls

### Original Design
> "Max-claims-per-day cap."

### Critique

1. **Per-claim agent calls are expensive**: Cursor agent startup, tool loading,
   potential browsing = ~$0.50-2.00 per claim at Opus rates. 10 claims/day =
   $5-20/day just for DelphiCursor.

2. **Batching is risky**: Multi-claim sessions risk state leakage (agent
   remembers prior claims), prompt-length limits, and single-point-of-failure
   (one crash loses all).

3. **No cost visibility**: The design doesn't specify how to track spend or
   alert on budget exhaustion.

4. **No priority queue**: All eligible claims treated equally, but some
   (explicit owner escalation, older deadlocks) should jump the queue.

### Improved Design

**Architecture: Hybrid single-claim + soft batching**

- **Default**: One agent call per claim (isolation, reliability).
- **Soft batching**: If queue depth > 5 at start of run, agent receives up to 3
  claims in one session with explicit instructions to judge each independently
  and write separate verdict files.
- **Hard cap**: 15 claims/day, 100 claims/month (adjustable in config).

**Cost tracking**:
- Worker logs estimated cost per claim to `data/delphicursor_costs.jsonl`:
  ```json
  {"claim_id": "...", "timestamp": "...", "model": "opus", "est_cost_usd": 1.20, "batched_with": []}
  ```
- Daily summary written to `data/delphicursor_cost_summary.json`.
- If monthly spend > 80% of budget, worker pauses and alerts owner.

**Priority queue** (processed in order):
1. `delphicursor_status: urgent` (owner override)
2. `delphicursor_status: queued` with oldest `testing_since`
3. Auto-escalated by trigger logic (§1), scored by deadlock severity

**Batching contract** (if used):
```
You will judge {N} predictions in this session. For EACH prediction:
1. Read its fixture from data/delphicursor_queue/{claim_id}.json
2. Judge it independently — do NOT let your judgment on one claim influence another
3. Write your verdict to data/delphicursor_verdicts/{claim_id}.json

After writing all {N} verdicts, write a completion marker to
data/delphicursor_verdicts/_batch_{batch_id}_done.txt
```

### Open Questions for Owner
- What's the monthly budget ceiling? ($50? $100? $200?)
- Should the worker auto-pause at 80%, or just warn?
- Is soft batching acceptable, or strict single-claim isolation required?
- Should cost be visible in the UI (e.g., "This verdict cost $1.40")?

---

## 4. Precedence Stack Interaction

### Original Design
> "Display precedence stays: Fact-Check > Marty > DelphiCursor > Delphi3080 >
> Panel > Swarm."

### Critique

1. **Can DelphiCursor flip a fact-check?** The design says no, but what if the
   "fact-check" was a simulated panelist (AP Fact Check) that hallucinated?
   The current system has FactCheck.org etc. as regular panelists with weight
   1.0 — they're not actually authoritative lookups.

2. **Marty override**: If Marty's verdict is FINAL and above DelphiCursor in
   precedence, then DelphiCursor can never disagree with Marty in the display.
   What's the point? It should either:
   - Be an **approval gate** (Opus judges, Marty confirms/overrides), or
   - Be **advisory-only** on Marty-marked claims (shown but not controlling).

3. **No feedback loop**: If DelphiCursor disagrees with Panel/Swarm, that
   information is useful for calibrating those systems — but the design has no
   mechanism for surfacing systematic disagreements.

4. **Authoritative vs. simulated fact-check confusion**: The current data has
   "FactCheck.org (simulated)" as a panelist. That's NOT a fact-check lookup —
   it's an LLM roleplaying. True authoritative verdicts need a separate field
   (`verdict_source: authoritative`, `authoritative_source: AP`, etc.).

### Improved Design

**Clarified precedence stack**:

| Tier | Source | Can Override? | Notes |
|------|--------|---------------|-------|
| 1 | **Authoritative Fact-Check** | Nothing | Requires `verdict_source: authoritative` + human-verified citation |
| 2 | **Marty's Verdict** | Only by explicit re-mark | Owner is FINAL; DelphiCursor is advisory |
| 3 | **DelphiCursor** | Overrides Delphi3080/Panel/Swarm | Frontier model tiebreaker |
| 4 | **Delphi3080** | Overrides Panel/Swarm | Full agent-society adjudication |
| 5 | **Panel** | Overrides Swarm | Weighted expert simulation |
| 6 | **Swarm** | Baseline | 40 persona votes |

**DelphiCursor vs. Marty interaction modes** (config choice):

- **Mode A: Advisory** (default): If Marty marked the claim, DelphiCursor still
  runs but its verdict is shown as "Opus thinks: X" alongside Marty's FINAL
  verdict. Useful for calibration/second opinion.

- **Mode B: Approval gate**: DelphiCursor runs BEFORE Marty marks. Owner sees
  Opus's recommendation and can accept, reject, or override. Useful for
  high-volume grading.

- **Mode C: Never run on Marty-marked**: Original behavior. DelphiCursor
  skipped entirely if `marty_verdict` exists.

**Fact-check clarity**:

- Rename simulated fact-checker panelists to avoid confusion:
  `"AP Fact Check (simulated)"` → `"AP-style analyst (simulated)"`
- True authoritative verdicts require:
  ```json
  {
    "verdict_source": "authoritative",
    "authoritative_source": "AP News",
    "authoritative_url": "https://apnews.com/article/...",
    "authoritative_quote": "The election was certified on Jan 6...",
    "authoritative_checked_by": "marty",
    "authoritative_checked_at": "2026-10-07"
  }
  ```
- **DelphiCursor cannot override authoritative verdicts** — but it can FLAG
  them for re-review if it strongly disagrees (logged, not auto-changed).

**Disagreement logging**:

When DelphiCursor disagrees with a lower-tier verdict:
```json
{
  "claim_id": "...",
  "delphicursor_vote": "incorrect",
  "disagreed_with": ["swarm", "panel"],
  "swarm_said": "RIGHT (72%)",
  "panel_said": "correct (score 2.25)",
  "delphicursor_reasoning": "..."
}
```
Written to `data/delphicursor_disagreements.jsonl` for calibration analysis.

### Open Questions for Owner
- Which mode (A/B/C) for Marty interaction? Advisory seems most useful.
- Should the owner see a notification when DelphiCursor strongly disagrees
  with an authoritative fact-check? (Could indicate a bad fact-check.)
- Should disagreement rate (DelphiCursor vs. Swarm/Panel) be tracked as a
  system health metric?

---

## 5. Failure Modes Unique to Cursor Agent CLI

### Original Design
> "Agent writes STATUS.md on failure; worker marks error and retries (max 2)."

### Critique

1. **State leakage between claims**: If the same agent session (or a session
   that reads prior outputs) processes multiple claims, judgments can bleed.
   Even "fresh" sessions may have workspace files from prior runs.

2. **Workspace pollution**: The agent can write arbitrary files. A buggy or
   adversarial prompt could lead to verdict files being overwritten, config
   modified, or repo state corrupted.

3. **Nondeterminism**: Same claim, same prompt → different verdicts on
   different runs. Opus has temperature; tool call timing varies; browsing
   returns different results.

4. **Agent wandering**: The instruction says "write to this file" but the
   agent might decide to read other files, run commands, or explore the repo.
   This is wasted tokens and potential contamination.

5. **Stdout unreliability**: Per OPERATIONS.md, stdout capture is lossy. The
   design correctly uses file-based output — but doesn't specify what happens
   if the file is malformed or missing.

6. **Timeout handling**: A claim about a complex topic might lead to extended
   browsing. The design doesn't specify timeouts or how to handle runaway
   agents.

7. **Concurrency**: If two worker instances run, they could process the same
   claim simultaneously, leading to race conditions on verdict files.

### Improved Design

**Isolation guarantees**:

- **Fresh workspace per claim**: Worker creates a temp directory
  (`data/delphicursor_workspace/{claim_id}/`) containing ONLY the fixture file.
  Agent writes verdict there. After success, worker moves verdict to final
  location and deletes workspace.

- **No repo access**: Agent prompt explicitly says:
  ```
  You are running in an isolated workspace. The only files you should read are:
  - claim_fixture.json (the prediction to judge)

  The only file you should write is:
  - verdict.json (your judgment)

  Do NOT explore other directories. Do NOT read or modify any other files.
  ```

- **Workspace allowlist** (if Cursor supports): Restrict agent file access to
  the workspace directory only.

**Nondeterminism mitigation**:

- **Log full agent output**: Capture stdout/stderr to
  `data/delphicursor_logs/{claim_id}_{timestamp}.log` for debugging.

- **Verdict validation**: Worker validates verdict JSON against schema before
  accepting. Invalid → retry once with "Your previous output was malformed.
  Please output valid JSON."

- **Determinism flag**: If Cursor CLI supports `--temperature 0`, use it.

**Timeout and runaway handling**:

- **Hard timeout**: 5 minutes per claim. Worker kills agent process after
  timeout, marks `delphicursor_status: timeout`.

- **Soft timeout warning**: At 3 minutes, if no verdict file exists, worker
  logs a warning (but doesn't interrupt).

- **Browse limit**: If possible, instruct agent to check max 2 external URLs.

**Concurrency control**:

- **File lock**: Worker acquires `data/delphicursor.lock` before processing.
  Only one worker instance runs at a time.

- **Claim lock**: Before processing claim X, worker writes
  `data/delphicursor_workspace/{claim_id}/.processing` with worker PID and
  timestamp. Other workers skip claims with recent `.processing` files.

**Failure classification**:

| Failure | Detection | Action |
|---------|-----------|--------|
| No verdict file | Worker checks after timeout | Mark `error`, retry once |
| Malformed JSON | Schema validation | Retry with correction prompt |
| Agent crash | Non-zero exit code | Mark `error`, retry once |
| Timeout | 5 min elapsed | Mark `timeout`, no retry (likely hard claim) |
| Verdict outside schema | Vote not in `correct\|incorrect\|unclear` | Retry with correction |
| Wandering detected | Agent touched files outside workspace | Mark `contaminated`, alert owner |

**Retry policy**:

- Max 2 attempts per claim.
- After 2 failures, mark `delphicursor_status: failed_permanent`.
- Failed claims are logged to `data/delphicursor_failures.jsonl` with full
  error context for manual review.

### Open Questions for Owner
- Should workspace isolation be enforced at the Cursor CLI level (if possible)
  or just via prompt instructions?
- Is 5 minutes too long/short for complex claims?
- Should failed claims be retried on next day's run, or require manual re-queue?
- Should there be a "canary claim" test at worker startup to verify agent is
  behaving correctly before processing real claims?

---

## Summary of Key Changes from v1

| Area | v1 | v2 |
|------|----|----|
| Trigger | Marty vs panel disagreement | Multi-factor escalation (margin, deadlock, recency, weight) |
| Marty position in prompt | Included | **Redacted** (blind judgment) |
| Batching | Implied single-claim | Hybrid: single + soft batch (3 max) |
| Cost tracking | None | Per-claim logging, monthly budget cap |
| Precedence | Fixed stack | Clarified + modes for Marty interaction |
| Fact-check | Ambiguous | Distinct authoritative vs. simulated |
| Isolation | None | Workspace per claim, file allowlist |
| Timeout | None | 5 min hard limit |
| Retry | Max 2, vague | Structured policy with failure classification |

---

## Implementation Checklist (for when approved)

This section is for planning only — DO NOT implement without owner approval.

- [ ] Add `delphicursor_status` field to prediction schema
- [ ] Build trigger logic (§1) as `scripts/delphicursor_queue.py`
- [ ] Build fixture writer with Marty redaction
- [ ] Build worker `scripts/delphicursor_worker.py` with isolation, timeout, retry
- [ ] Add cost tracking and budget enforcement
- [ ] Update render.py to display DelphiCursor verdicts
- [ ] Add disagreement logging
- [ ] Add configuration for Marty interaction mode (A/B/C)
- [ ] Rename simulated fact-checker panelists
- [ ] Document authoritative fact-check schema

---

**Document version**: v2 (2026-10-07)
**Author**: Design critique by AI assistant
**Status**: DESIGN ONLY — awaiting owner review and approval
