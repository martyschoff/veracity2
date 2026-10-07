# DelphiCursor — Design v3 (FINAL CONSOLIDATED)

**Status:** DESIGN ONLY. Nothing implemented. Awaiting owner approval.

This document consolidates v1 (owner decisions, grid labeling) and v2 (critique
improvements) into the final specification. Owner decisions from 2026-10-07 are
incorporated as settled; remaining open questions are minimized.

---

## Owner Decisions (SETTLED)

| Decision | Resolution |
|----------|------------|
| **Operating Mode** | Mode A: Advisory. Marty's verdict is FINAL; DelphiCursor runs anyway and both verdicts display side by side for calibration. |
| **Budget Model** | Flat-fee Cursor subscription. No per-dollar accounting. Only a rate cap (max claims/day). |
| **Grid Labeling** | Distinct labels for both Delphi variants (see §7 below). |

---

## 1. Purpose

DelphiCursor uses **Cursor (Opus)** as an advisory adjudicator alongside the
local Delphi3080 agent-society simulation. Benefits:

- Opus-level reasoning with live web context (no knowledge-cutoff hallucinations)
- No Neo4j/Graphiti dependency — pure prompt adjudication
- Calibration signal: compare Opus's blind judgment against Marty's final mark

DelphiCursor **does not override Marty**. It provides a second opinion visible
on the card for tracking model-vs-human agreement over time.

---

## 2. When DelphiCursor Runs (Escalation Trigger)

### Multi-Factor Trigger

A prediction becomes eligible for DelphiCursor if **any 2+ factors** are true:

| Factor | Condition | Rationale |
|--------|-----------|-----------|
| **Swarm split** | `mc_split ≤ 35` (i.e., 35-65 or tighter) | Genuine disagreement among personas |
| **Delphi3080 unclear** | `miro_result.verdict == "unclear"` OR `miro_status == "error"` | Heavy machinery couldn't decide |
| **Recency-sensitive** | Claim references events after 2024-01-01 | Opus has live knowledge; local models have cutoff |
| **High-weight predictor** | Predictor's `panel_weight ≥ 1.25` | Track record matters more |
| **Explicit queue** | Owner sets `delphicursor_status: queued` | Manual override |

### Threshold Stress-Test (Based on Actual Data)

Current swarm data from `scripts/monte_carlo.py` (40 personas):

| mc_split | mc_result | Would Trigger? |
|----------|-----------|----------------|
| 0 | WRONG (0% of 10 decided, 30 unclear) | ✅ Yes (split ≤ 35) |
| 0 | WRONG (0% of N decided, all unclear) | ✅ Yes |
| 33 | WRONG (33% of 3 decided, 33 unclear) | ✅ Yes (33 ≤ 35) |
| 38 | WRONG (38% of 24 decided, 16 unclear) | ❌ No (38 > 35) |

**Rationale for ≤35 threshold**: A 35-65 split means 35% minority — still a
meaningful disagreement. The 38% split (24 decided) represents a clearer
majority view and doesn't need escalation. The ≤30 threshold from v2 was too
tight; ≤35 captures the genuinely contested cases in our data while avoiding
escalation on decisive votes.

**Edge case**: When `mc_split = 0` with few `decided` voters (e.g., "0% of 3
decided, 37 unclear"), this indicates mass uncertainty, not consensus —
escalation is appropriate.

### Exclusions (Never Queue)

- `verdict_source: authoritative` (fact-checked with human-verified citation)
- `test_status != eligible` (not yet due for judgment)
- Already has a valid `delphicursor_result` (no re-runs without explicit queue)

### Daily Rate Cap

- **Max 15 claims/day** (flat-fee subscription removes dollar constraint)
- Priority order:
  1. `delphicursor_status: urgent` (explicit owner escalation)
  2. `delphicursor_status: queued` (owner queued)
  3. Auto-escalated by trigger, sorted by `mc_split` ascending (most contested first)

---

## 3. Fixture Schema (Claim Input)

Written to `data/delphicursor_workspace/{claim_id}/claim_fixture.json`:

```json
{
  "claim_id": "pred_xxx",
  "statement": "<the prediction text>",
  "made_by": "<individual name>",
  "made_on": "<date>",
  "category": "<ai|finance|geopolitics|energy|china|other>",
  "time_horizon": "<target year or 'ongoing'>",
  "transcript_excerpt": "<supporting quote, max 800 chars>",
  "source_url": "<link to original>",

  "adjudication_context": {
    "swarm_result": "WRONG (38% of 24 decided, 16 unclear)",
    "swarm_split": 38,
    "delphi3080_verdict": "unclear",
    "delphi3080_status": "error | done",
    "panel_votes_summary": "2 correct (w=2.25), 1 unclear (w=1.0)"
  }
}
```

**Critical**: Marty's position is **NEVER** in the fixture. The agent judges
blind to prevent sycophantic anchoring.

---

## 4. Prompt Contract

**System message** (written to workspace alongside fixture):

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
   your source if you do. Max 2 external URLs.
3. Do NOT default to "unclear" out of excessive caution. If you have a
   defensible position, commit to it.
4. Do NOT default to "correct" or "incorrect" out of false confidence. If the
   evidence is ambiguous, say UNCLEAR.
5. Predictions about the future that haven't happened yet are NOT automatically
   unclear — judge whether they are ON TRACK or OFF TRACK based on current
   evidence.
6. Confidence should reflect YOUR epistemic state, not the prediction's
   boldness.

OUTPUT: Write a JSON file to verdict.json in your workspace:
{
  "vote": "correct" | "incorrect" | "unclear",
  "confidence": 0-100,
  "reasoning": "2-3 sentences explaining your judgment",
  "sources_checked": ["url1", "url2"] or [],
  "dissent_note": "Why you disagree with swarm/delphi3080, if you do"
}
```

---

## 5. Invocation & Isolation

### Workspace Isolation

Each claim runs in an isolated directory:

```
data/delphicursor_workspace/{claim_id}/
  ├── claim_fixture.json    # Input (written by worker)
  ├── system_prompt.txt     # Prompt (written by worker)
  └── verdict.json          # Output (written by agent)
```

The agent prompt explicitly restricts file access:

```
You are running in an isolated workspace. The only files you should read are:
- claim_fixture.json (the prediction to judge)
- system_prompt.txt (your instructions)

The only file you should write is:
- verdict.json (your judgment)

Do NOT explore other directories. Do NOT read or modify any other files.
```

### Agent Invocation

```bash
agent.cmd --trust --model opus -p "Read system_prompt.txt and claim_fixture.json, then write verdict.json"
```

Working directory: `data/delphicursor_workspace/{claim_id}/`

### Timeout & Retry

| Parameter | Value |
|-----------|-------|
| Hard timeout | 5 minutes |
| Soft warning | 3 minutes (logged, no interrupt) |
| Max retries | 2 per claim |
| Retry trigger | No verdict file, malformed JSON, or schema violation |

### Failure Classification

| Failure | Detection | Action |
|---------|-----------|--------|
| No verdict file | Check after timeout | Mark `error`, retry |
| Malformed JSON | Schema validation | Retry with correction hint |
| Vote outside schema | Not `correct\|incorrect\|unclear` | Retry with correction |
| Timeout | 5 min elapsed | Mark `timeout`, no retry |
| Agent wandered | Touched files outside workspace | Mark `contaminated`, alert |

After 2 failures: `delphicursor_status: failed_permanent`, logged to
`data/delphicursor_failures.jsonl`.

---

## 6. Output & Merge

### Verdict Storage

On success, worker moves verdict to permanent location:

```
data/delphicursor_verdicts/{claim_id}.json
```

### Field Written to Prediction

```json
{
  "delphicursor_status": "done",
  "delphicursor_result": {
    "vote": "incorrect",
    "confidence": 78,
    "reasoning": "...",
    "sources_checked": [],
    "dissent_note": "Swarm was 62% RIGHT but evidence shows...",
    "judged_at": "2026-10-07T14:30:00Z"
  }
}
```

### Display Precedence Stack

| Tier | Source | Controls Display? | Notes |
|------|--------|-------------------|-------|
| 1 | **Authoritative Fact-Check** | Yes | `verdict_source: authoritative` |
| 2 | **Marty's Verdict** | Yes (FINAL) | `marty_agrees`, `marty_note` |
| 3 | **DelphiCursor** | **Advisory only** | Shown alongside Marty, not controlling |
| 4 | **Delphi3080** | Yes (if no Marty) | `miro_result` |
| 5 | **Panel** | Yes (if no Delphi) | `judgements[]` weighted |
| 6 | **Swarm** | Yes (baseline) | `mc_result` |

**Mode A behavior**: When Marty has marked a prediction, the card shows:
- Marty's verdict as the **controlling** result
- DelphiCursor's verdict as **"Opus advisory"** for comparison

---

## 7. Grid Labeling (Card Display)

Distinct labels prevent confusion when multiple verdicts coexist:

| Source | Label | Subtitle |
|--------|-------|----------|
| Delphi3080 | "Delphi3080" | "agent-society sim — local 32B" |
| DelphiCursor | "DelphiCursor" | "Opus — advisory" |
| Swarm | "Swarm" | "40 personas" |
| Panel | "Panel" | "weighted votes" |
| Marty | "Marty" | "final" |
| Fact-Check | "Fact-Check" | "authoritative" |

**Example card line:**
```
Marty: Wrong (final) — Delphi3080: Unclear — DelphiCursor: Wrong (advisory) — Swarm: 38% RIGHT
```

---

## 8. Logging & Observability

### Per-Claim Log

`data/delphicursor_logs/{claim_id}_{timestamp}.log` — full agent stdout/stderr.

### Disagreement Tracking

When DelphiCursor disagrees with Swarm or Delphi3080, append to
`data/delphicursor_disagreements.jsonl`:

```json
{
  "claim_id": "pred_xxx",
  "timestamp": "2026-10-07T14:30:00Z",
  "delphicursor_vote": "incorrect",
  "delphicursor_confidence": 78,
  "swarm_said": "RIGHT (62%)",
  "delphi3080_said": "unclear",
  "marty_said": "Wrong"
}
```

### Daily Summary

`data/delphicursor_summary_{date}.json`:
```json
{
  "date": "2026-10-07",
  "claims_processed": 12,
  "verdicts": {"correct": 3, "incorrect": 7, "unclear": 2},
  "agreed_with_marty": 9,
  "disagreed_with_marty": 3,
  "failures": 1
}
```

---

## 9. Concurrency Control

- **Global lock**: `data/delphicursor.lock` — only one worker runs at a time
- **Claim lock**: `data/delphicursor_workspace/{claim_id}/.processing` with PID/timestamp
- Workers skip claims with `.processing` files < 10 minutes old

---

## 10. Remaining Open Questions (MINIMAL)

| # | Question | Default if Unspecified |
|---|----------|------------------------|
| 1 | Should failed claims auto-retry next day, or require manual re-queue? | Manual re-queue |
| 2 | Should DelphiCursor run a "canary claim" at startup to verify agent health? | No (add latency) |
| 3 | Should disagreement alerts (Opus strongly disagrees with Marty) notify owner? | Log only |

All other questions from v2 are resolved by owner decisions (Mode A, flat-fee).

---

## Implementation Checklist (For When Approved)

**DO NOT IMPLEMENT** without owner approval.

- [ ] Add `delphicursor_status` field to prediction schema
- [ ] Build trigger logic as `scripts/delphicursor_queue.py`
- [ ] Build fixture writer with Marty redaction
- [ ] Build worker `scripts/delphicursor_worker.py` (isolation, timeout, retry)
- [ ] Update `render.py` for dual-verdict card display
- [ ] Add disagreement logging
- [ ] Add daily summary generation

---

## Appendix: Threshold Calibration Notes

Based on current `predictions.json` data (2026-10-07):

- **7 predictions** have `mc_split` values
- **Distribution**: 0 (×4), 33, 38 — limited sample, but pattern is clear
- **Zero splits** indicate mass uncertainty (few decided), not consensus
- **≤35 threshold** captures splits at 33 and below while excluding 38+
- **Panel weights** range 1.0–1.25; `≥1.25` threshold selects domain experts

As more swarm data accumulates, revisit threshold if:
- Too few escalations: loosen to ≤40
- Too many escalations: tighten to ≤30

---

**Document version**: v3 FINAL (2026-10-07)  
**Supersedes**: DELPHICURSOR_DESIGN.md (v1), DELPHICURSOR_DESIGN_V2.md (v2)  
**Status**: DESIGN ONLY — awaiting owner approval
