#!/usr/bin/env python3
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / 'data' / 'predictions.json'

with open(DATA_FILE, 'r', encoding='utf-8') as f:
    raw = json.load(f)

predictions = raw.get('predictions', [])

# Check Peter Zeihan's data
zeihan_preds = [p for p in predictions if p.get('individual_name') == 'Peter Zeihan']
resolved = [p for p in zeihan_preds if p.get('verdict') in ['correct', 'wrong', 'incorrect']]

print(f"Peter Zeihan total predictions: {len(zeihan_preds)}")
print(f"Peter Zeihan resolved predictions: {len(resolved)}")

if resolved:
    correct_count = sum(1 for p in resolved if p.get('verdict') == 'correct')
    print(f"Correct: {correct_count}")
    print(f"Accuracy: {correct_count / len(resolved):.2%}")
    
    # Check one example with judgements
    with_judgements = [p for p in resolved if p.get('judgements')]
    print(f"Predictions with judgements: {len(with_judgements)}")
    
    if with_judgements:
        example = with_judgements[0]
        print(f"Example prediction: {example.get('claim', '')[:100]}...")
        print(f"Verdict: {example.get('verdict')}")
        print(f"Judgements: {len(example.get('judgements', []))}")
        for j in example.get('judgements', [])[:3]:
            print(f"  - {j.get('panelist')}: {j.get('verdict')} (weight: {j.get('weight', 1.0)})")