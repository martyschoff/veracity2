#!/usr/bin/env python3
import json, os, math
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / 'data' / 'predictions.json'

with open(DATA_FILE, 'r', encoding='utf-8') as f:
    raw = json.load(f)

predictions = raw.get('predictions', [])

def wilson_confidence_interval(correct, total, confidence=0.95):
    """Calculate Wilson score confidence interval for proportion."""
    if total == 0:
        return (0.0, 0.0)
    if total == 1:
        return (0.0, 1.0) if correct == 1 else (0.0, 0.0)
    
    p = correct / total
    z = 1.96 if confidence == 0.95 else 2.576  
    
    denominator = 1 + z**2 / total
    centre_adjusted_probability = (p + z**2 / (2 * total)) / denominator
    adjusted_standard_deviation = math.sqrt(max(0, (p * (1 - p) + z**2 / (4 * total)) / total)) / denominator
    
    lower = centre_adjusted_probability - z * adjusted_standard_deviation
    upper = centre_adjusted_probability + z * adjusted_standard_deviation
    
    return (max(0.0, lower), min(1.0, upper))

def compute_panel_probability(judgements):
    """Compute P_panel per claim from judgements."""
    if not judgements:
        return None
        
    correct_weight = sum(j.get('weight', 1.0) for j in judgements if j.get('verdict') == 'correct')
    total_weight = sum(j.get('weight', 1.0) for j in judgements if j.get('verdict') in ['correct', 'wrong', 'incorrect'])
    
    if total_weight == 0:
        return None
    
    return correct_weight / total_weight

def compute_person_scores(predictions, person_name):
    """Compute accuracy and Brier scores for a person."""
    person_preds = [p for p in predictions if p.get('individual_name') == person_name]
    resolved_preds = [p for p in person_preds if p.get('verdict') in ['correct', 'wrong', 'incorrect']]
    
    if not resolved_preds:
        return None
    
    correct_count = sum(1 for p in resolved_preds if p.get('verdict') == 'correct')
    accuracy = correct_count / len(resolved_preds)
    lower, upper = wilson_confidence_interval(correct_count, len(resolved_preds))
    
    base_rate = accuracy
    
    brier_claims = []
    for pred in resolved_preds:
        judgements = pred.get('judgements', [])
        p_panel = compute_panel_probability(judgements)
        if p_panel is not None:
            p_adjusted = 0.7 * p_panel + 0.3 * base_rate
            outcome = 1.0 if pred.get('verdict') == 'correct' else 0.0
            
            brier_shrunk = (p_adjusted - outcome) ** 2
            brier_raw = (p_panel - outcome) ** 2
            
            brier_claims.append({
                'brier_shrunk': brier_shrunk,
                'brier_raw': brier_raw,
                'outcome': outcome
            })
    
    if brier_claims:
        avg_brier_shrunk = sum(c['brier_shrunk'] for c in brier_claims) / len(brier_claims)
        avg_brier_raw = sum(c['brier_raw'] for c in brier_claims) / len(brier_claims)
        base_rate_brier = base_rate * (1 - base_rate)  
        skill = base_rate_brier - avg_brier_shrunk
    else:
        avg_brier_shrunk = avg_brier_raw = skill = None
        
    return {
        'accuracy': accuracy,
        'accuracy_ci': (lower, upper),
        'n_resolved': len(resolved_preds),
        'n_brier': len(brier_claims),
        'brier_shrunk': avg_brier_shrunk,
        'brier_raw': avg_brier_raw,
        'skill': skill,
        'base_rate': base_rate,
        'display_scores': len(resolved_preds) >= 10
    }

# Test with Peter Zeihan
scores = compute_person_scores(predictions, 'Peter Zeihan')
print(f"Peter Zeihan scores: {scores}")

if scores and scores['accuracy'] is not None:
    acc_pct = int(scores['accuracy'] * 100)
    ci_lower = int(scores['accuracy_ci'][0] * 100)
    ci_upper = int(scores['accuracy_ci'][1] * 100)
    print(f"Display: Accuracy {acc_pct}% (N={scores['n_resolved']}, {ci_lower}-{ci_upper}%)")
    
    if scores['brier_shrunk'] is not None:
        skill_str = f"+{scores['skill']:.2f}" if scores['skill'] > 0 else f"{scores['skill']:.2f}"
        print(f"Display: Brier {scores['brier_shrunk']:.2f} (shrunk, N={scores['n_brier']}) | raw {scores['brier_raw']:.2f} | Skill {skill_str}")

# Test with others
for name in ['Doomberg', 'Peter Diamandis', 'Ian Bremmer', 'David McAlvany']:
    scores = compute_person_scores(predictions, name)
    if scores:
        print(f"{name}: N={scores['n_resolved']}, Accuracy={scores['accuracy']:.1%}, Brier claims={scores['n_brier']}")