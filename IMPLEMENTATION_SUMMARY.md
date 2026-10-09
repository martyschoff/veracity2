# Scoring Implementation Summary

## Completed Implementation

This implements the dual scoring system exactly as specified in `data/sonnet_scoring_impl_prompt.txt`:

### 1. Accuracy + Wilson CI 
- **Function**: `wilson_confidence_interval(correct, total, confidence=0.95)`
- **Display**: "Accuracy 92% (N=108, 85-96%)" format
- **Location**: Individual scorecard sections in templates/index.html

### 2. Brier with shrinkage
- **Formula**: `P_adjusted = 0.7 * P_panel + 0.3 * base_rate`
- **Metrics**: Brier shrunk, Brier raw, Skill score
- **Display**: "Brier .21 (shrunk, N=108) | raw .24 | Skill +.03" format

### 3. Per-person scoring
- **Tracked**: Zeihan, Doomberg, Diamandis, Bremmer, McAlvany
- **Extended**: Any person with N>=1 resolved claims
- **Rules**: N>=10 full display, N<10 grayed

### 4. Data processing choices
- **Verdicts**: Handle both 'wrong' and 'incorrect' as negative
- **Resolved**: Include 'correct', 'wrong', 'incorrect' verdicts only
- **Edge cases**: Skip claims with no decisive votes for Brier calculation

### 5. Files modified
- **render.py**: Added all scoring calculation functions
- **templates/index.html**: Added scoring display in scorecard sections

## Ready for commit and push
The implementation is complete and will display scoring metrics when render.py is executed.