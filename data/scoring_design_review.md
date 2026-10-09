# Scoring design to assess (blunt statistical review requested)

## Context data (measured, real)
- 1,267 predictions; 280 panel-resolved (216 correct, 57 wrong, 7 expired); 8 swarm results; 11 DelphiCursor verdicts (confidence 0-100 self-report); 9 Delphi3080 verdicts (confidence 0-1 self-report).
- Per-claim panel: 3 simulated panelists vote correct/wrong/unclear with weights 1.0/1.25/1.5. Implied probability P = sum(weight of 'correct' votes) / sum(weight of decisive votes). Coarse scale: with 3 voters P lands near {0, 0.29, 0.43, 0.57, 0.71, 1.0}.
- 215 of 273 claims have >=2 decisive votes.
- Per-person resolved N: Bremmer 111, Zeihan 108, Doomberg 33, McAlvany 20, Diamandis 1, all new panelists 0-4.
- 400-persona swarm test showed: 400 agrees with 40 on 5/5 verdicts but 'unclear' balloons (194-311 of 400) - the decided core is what carries probability info.

## Proposed display
Per-person header box adds (under existing thumbs): "Brier .21 (panel, N=108) - Cal +9% - Skill +.08"

- Variant A (default, marked 'panel'): Brier over resolved claims using P_panel (weighted vote share). Calibration: bucket claims by P (<0.4, 0.4-0.6, >0.6), compare bucket avg P vs actual rate. Display 'Cal +-X%' as mean |P - rate| deviation or similar.
- Variant B (marked 'mixed'): same math but P from hierarchy DelphiCursor conf -> Delphi3080 conf -> swarm % -> panel share, with per-source normalization before mixing. Shown only where sources differ from panel.
- Skill = (base-rate Brier for that person's claims) - (person's Brier). Positive = beats base rate.
- N>=10 to display; otherwise grayed with 'N=x'.

## Known issues acknowledged in design
(a) unanimity trap - unanimous P=1.0 claims cost full Brier point if wrong; near-unanimity is common with 3 voters
(b) this scores THE PANEL'S judgment of the person, not the person's own calibration (speaker stated-probabilities rarely extractable)
(c) swarm 'unclear' mass excluded from P (only decided votes counted)

## Questions
1. Statistical flaws in this design?
2. Is Variant B worth building at all, given the scale-mismatch problem and tiny N?
3. Better calibration display than 3 coarse buckets for 3-voter panels?
4. How should unanimity be handled (raw, or shrunk toward base rate)?
5. Anything in the unclear-ballooning / coarse-P-scale data that breaks the math?
6. Final verdict: ship / fix-then-ship (list) / redesign?

Answer directly - do NOT modify files.