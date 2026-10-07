# DelphiCursor — Design (NOT implemented; awaiting approval)

An alternative Delphi adjudicator that uses **Cursor (Opus)** as the judge instead
of the local 32B panel stack. Same claim-in/verdict-out contract as Delphi3080.

## Why it might matter
- Opus-level reasoning per claim; no knowledge-cutoff hallucinations on public
  facts (Cursor's model has web/live context).
- No Neo4j/Graphiti dependency — a pure prompt adjudication like the weighted
  panel, but with a frontier model.

## Design
1. **Queue**: reuses `miro_status` OR a new `delphicursor_status` (design choice:
   separate field — keeps the two Delphi variants independent and lets us A/B them).
2. **Prompt contract**: same JSON schema as the panel
   (`{"vote": "correct|incorrect|unclear", "reasoning": ...}`) plus a
   `confidence` and `sources_considered` field — Opus is allowed (encouraged)
   to browse before voting.
3. **Invocation**: Cursor agent CLI (`agent.cmd --trust --model opus -p <prompt>`)
   with the claim fixture written to a temp file (same pattern as the Opus panel
   reviews). Each claim = one agent call, ~1-3 min.
4. **Output capture**: the agent WRITES its verdict JSON to
   `data/delphicursor_verdicts/<pred_id>.json` (stdout is unreliable per OPERATIONS.md).
5. **Merge**: worker reads verdict files, writes `delphicursor_result` on the
   prediction. Display precedence stays: Fact-Check > Marty > DelphiCursor >
   Delphi3080 > Panel > Swarm.
6. **Cost control**: Cursor budget is finite — batch mode with a max-claims-per-day
   cap, reserved for high-stakes or Marty-contested predictions (e.g. run
   DelphiCursor only when Marty and the panel disagree).
7. **Failure handling**: agent writes STATUS.md on failure; worker marks
   `delphicursor_status: error` and retries next cycle (max 2).

## Open questions (for the owner)
- Reserved for disagreements only, or run on every graded prediction?
- Cursor subscription budget cap per month?

## GRID LABELING (design, 2026-10-07)
Card display names must be unmistakable now that two Delphi verdicts can
co-exist on one card:
- Delphi3080 -> label "Delphi3080" (sub: "agent-society sim - local 32B")
- DelphiCursor -> label "DelphiCursor" (sub: "Opus - advisory")
- Swarm -> "Swarm" (sub: "40 personas"); Panel -> "Panel" (sub: "weighted votes")
- Marty -> "Marty" (sub: "final"); Fact-Check -> "Fact-Check" (sub: "authoritative")
Example card line: "Marty: Right (final) - Delphi3080: Correct -
DelphiCursor: Wrong - Swarm: 65% on-track"

## OWNER DECISIONS (2026-10-07)
- **Mode A chosen**: DelphiCursor is advisory. Owner marks Marty Right/Left
  (final), and Opus runs too - the grid shows BOTH Delphi3080's verdict and
  Opus's (DelphiCursor) side by side on the card. Calibration by contrast.
- **Budget**: if the Cursor plan is flat-fee, the dollar-budget control is
  dropped; keep only a rate cap (max N claims/day, no $ accounting).

## Status
DESIGN ONLY. Nothing implemented. Do not build without owner approval.
