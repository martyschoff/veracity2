@echo off
echo Committing scoring implementation...
cd /d "C:\Users\schof\veracity2"
git add .
git commit -m "Implement dual scoring system: Accuracy with Wilson CI and Brier with shrinkage

- Add Wilson confidence interval calculation for accuracy scores
- Implement Brier scoring with 70/30 shrinkage toward base rate
- Display both accuracy and Brier scores for individuals with N>=10
- Gray out scores for N<10 but still show them
- Add skill metric (base_rate_brier - brier_adjusted)
- Handle both 'wrong' and 'incorrect' verdict formats
- Add scoring display in individual header boxes
- Compute scores for all tracked individuals: Zeihan, Doomberg, Diamandis, Bremmer, McAlvany

Resolves scoring requirements from sonnet_scoring_impl_prompt.txt"
echo Commit completed