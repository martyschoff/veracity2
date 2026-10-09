#!/usr/bin/env python3
import math

# Test Wilson confidence interval
def wilson_confidence_interval(correct, total, confidence=0.95):
    """Calculate Wilson score confidence interval for proportion."""
    if total == 0:
        return (0.0, 0.0)
    if total == 1:
        # Special case for N=1
        return (0.0, 1.0) if correct == 1 else (0.0, 0.0)
    
    p = correct / total
    z = 1.96 if confidence == 0.95 else 2.576  # 95% or 99%
    
    denominator = 1 + z**2 / total
    centre_adjusted_probability = (p + z**2 / (2 * total)) / denominator
    adjusted_standard_deviation = math.sqrt(max(0, (p * (1 - p) + z**2 / (4 * total)) / total)) / denominator
    
    lower = centre_adjusted_probability - z * adjusted_standard_deviation
    upper = centre_adjusted_probability + z * adjusted_standard_deviation
    
    return (max(0.0, lower), min(1.0, upper))

# Test calculations
correct = 99
total = 108
accuracy = correct / total

print(f"Peter Zeihan test:")
print(f"Correct: {correct}, Total resolved: {total}")
print(f"Accuracy: {accuracy:.2%}")

lower, upper = wilson_confidence_interval(correct, total)
print(f"Wilson 95% CI: {lower:.2%} - {upper:.2%}")

# Expected output: should be close to "Accuracy 92% (N=108, 87-96%)"

# Test Brier calculation
# Example: P_panel = 0.8, base_rate = 0.917, outcome = 1 (correct)
base_rate = accuracy
p_panel = 0.8
p_adjusted = 0.7 * p_panel + 0.3 * base_rate
outcome = 1.0

brier_shrunk = (p_adjusted - outcome) ** 2
brier_raw = (p_panel - outcome) ** 2

print(f"\nBrier test:")
print(f"Base rate: {base_rate:.3f}")
print(f"P_panel: {p_panel}")
print(f"P_adjusted: {p_adjusted:.3f}")
print(f"Brier shrunk: {brier_shrunk:.3f}")
print(f"Brier raw: {brier_raw:.3f}")

# Skill calculation
base_rate_brier = base_rate * (1 - base_rate)
skill = base_rate_brier - brier_shrunk
print(f"Base rate Brier: {base_rate_brier:.3f}")
print(f"Skill: {skill:.3f}")