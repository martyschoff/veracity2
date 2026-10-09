#!/usr/bin/env python3
print("Starting test render...")

try:
    import json, os, math
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    from pathlib import Path

    BASE = Path(__file__).resolve().parent
    DATA_FILE = BASE / 'data' / 'predictions.json'

    print(f"Loading data from {DATA_FILE}")
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        raw = json.load(f)

    predictions = raw.get('predictions', [])
    print(f"Loaded {len(predictions)} predictions")

    # Test Peter Zeihan data
    zeihan_preds = [p for p in predictions if p.get('individual_name') == 'Peter Zeihan']
    resolved = [p for p in zeihan_preds if p.get('verdict') in ['correct', 'wrong', 'incorrect']]
    correct = sum(1 for p in resolved if p.get('verdict') == 'correct')
    
    print(f"Peter Zeihan: {len(zeihan_preds)} total, {len(resolved)} resolved, {correct} correct")
    
    if resolved:
        accuracy = correct / len(resolved)
        print(f"Accuracy: {accuracy:.2%}")
    
    print("Test completed successfully")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()