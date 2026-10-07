"""DelphiCursor queue builder: identify predictions eligible for Opus adjudication.

Multi-factor escalation trigger (any 2+ factors → eligible):
- Swarm split ≤ 35 (genuine disagreement)
- Delphi3080 unclear or error
- Recency-sensitive (references events after 2024-01-01)
- High-weight predictor (panel_weight ≥ 1.25)
- Explicit queue (delphicursor_status: queued)

Usage: python scripts/delphicursor_queue.py [--dry-run]
"""
import argparse
import datetime
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_lock import locked_data

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / 'data' / 'predictions.json'

# Rate cap: max claims queued per day (flat-fee subscription, no $ accounting)
DAILY_CAP = 15

# Escalation thresholds
SWARM_SPLIT_THRESHOLD = 35  # mc_split ≤ 35 = genuine disagreement
HIGH_WEIGHT_THRESHOLD = 1.25  # panel_weight ≥ 1.25
RECENCY_CUTOFF = "2024-01-01"  # claims referencing events after this date


def is_recency_sensitive(claim: str) -> bool:
    """Check if claim references events after the recency cutoff."""
    # Look for years 2024, 2025, 2026, 2027+ in the claim text
    years = re.findall(r'\b(202[4-9]|203\d)\b', claim or '')
    return bool(years)


def count_escalation_factors(pred: dict, ind_weights: dict) -> tuple[int, list[str]]:
    """Count how many escalation factors apply to this prediction."""
    factors = []
    
    # Factor 1: Swarm split ≤ 35
    mc_split = pred.get('mc_split')
    if mc_split is not None and mc_split <= SWARM_SPLIT_THRESHOLD:
        factors.append(f"swarm_split={mc_split}")
    
    # Factor 2: Delphi3080 unclear or error
    miro_status = pred.get('miro_status')
    miro_result = pred.get('miro_result', {})
    miro_verdict = miro_result.get('verdict', '') if isinstance(miro_result, dict) else str(miro_result)
    if miro_status == 'error' or 'unclear' in miro_verdict.lower():
        factors.append(f"delphi3080={miro_status or miro_verdict[:20]}")
    
    # Factor 3: Recency-sensitive claim
    if is_recency_sensitive(pred.get('claim', '')):
        factors.append("recency_sensitive")
    
    # Factor 4: High-weight predictor
    predictor = pred.get('individual_name', '')
    weight = ind_weights.get(predictor, 1.0)
    if weight >= HIGH_WEIGHT_THRESHOLD:
        factors.append(f"high_weight={weight}")
    
    return len(factors), factors


def is_eligible(pred: dict, ind_weights: dict) -> tuple[bool, list[str]]:
    """Check if prediction is eligible for DelphiCursor queue."""
    # Exclusions (never queue)
    if pred.get('verdict_source') == 'authoritative':
        return False, ["excluded: authoritative"]
    if pred.get('test_status') not in (None, 'eligible'):
        return False, ["excluded: not_eligible"]
    if pred.get('delphicursor_status') in ('done', 'failed_permanent'):
        return False, ["excluded: already_processed"]
    if pred.get('delphicursor_result'):
        return False, ["excluded: has_result"]
    if pred.get('removed'):
        return False, ["excluded: removed"]
    if pred.get('gate_status'):
        return False, ["excluded: gated"]
    
    # Explicit queue override
    if pred.get('delphicursor_status') == 'queued':
        return True, ["explicit_queue"]
    if pred.get('delphicursor_status') == 'urgent':
        return True, ["explicit_urgent"]
    
    # Multi-factor trigger: need 2+ factors
    factor_count, factors = count_escalation_factors(pred, ind_weights)
    if factor_count >= 2:
        return True, factors
    
    return False, [f"only_{factor_count}_factors"]


def priority_key(pred: dict) -> tuple:
    """Sort key for queue priority (lower = higher priority)."""
    status = pred.get('delphicursor_status', '')
    
    # Priority 1: explicit urgent
    if status == 'urgent':
        return (0, pred.get('testing_since', '9999'))
    
    # Priority 2: explicit queued (oldest first)
    if status == 'queued':
        return (1, pred.get('testing_since', '9999'))
    
    # Priority 3: auto-escalated by mc_split ascending (most contested first)
    mc_split = pred.get('mc_split', 100)
    return (2, mc_split, pred.get('testing_since', '9999'))


def run(dry_run: bool = False):
    """Build the DelphiCursor queue."""
    with open(DATA, encoding='utf-8') as f:
        data = json.load(f)
    
    # Build individual weight lookup
    ind_weights = {i['name']: i.get('panel_weight', 1.0) for i in data.get('individuals', [])}
    
    predictions = data.get('predictions', [])
    eligible = []
    stats = {'total': 0, 'eligible': 0, 'excluded': 0, 'insufficient_factors': 0}
    
    for pred in predictions:
        stats['total'] += 1
        is_elig, reasons = is_eligible(pred, ind_weights)
        
        if is_elig:
            stats['eligible'] += 1
            eligible.append((pred, reasons))
        elif 'excluded' in reasons[0]:
            stats['excluded'] += 1
        else:
            stats['insufficient_factors'] += 1
    
    # Sort by priority and cap
    eligible.sort(key=lambda x: priority_key(x[0]))
    to_queue = eligible[:DAILY_CAP]
    
    print(f"DelphiCursor Queue Builder")
    print(f"==========================")
    print(f"Total predictions: {stats['total']}")
    print(f"Eligible: {stats['eligible']}")
    print(f"Excluded (already done/gated/etc): {stats['excluded']}")
    print(f"Insufficient factors (<2): {stats['insufficient_factors']}")
    print(f"Daily cap: {DAILY_CAP}")
    print(f"Will queue: {len(to_queue)}")
    print()
    
    if to_queue:
        print("Queue (priority order):")
        for i, (pred, reasons) in enumerate(to_queue, 1):
            status = pred.get('delphicursor_status', 'auto')
            print(f"  {i}. [{status}] {pred['id'][:30]}... | {', '.join(reasons)}")
            print(f"      {pred.get('claim', '')[:70]}...")
        print()
    
    if dry_run:
        print("[DRY RUN] No changes made.")
        return
    
    # Update predictions with queued status
    queued_ids = {p['id'] for p, _ in to_queue}
    changes = 0
    
    with locked_data() as fresh:
        for pred in fresh['predictions']:
            if pred['id'] in queued_ids:
                if pred.get('delphicursor_status') not in ('queued', 'urgent'):
                    pred['delphicursor_status'] = 'queued'
                    pred['delphicursor_queued_at'] = datetime.datetime.now().isoformat()
                    changes += 1
    
    print(f"Queued {changes} new predictions for DelphiCursor processing.")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true', help='Show what would be queued without making changes')
    args = ap.parse_args()
    run(dry_run=args.dry_run)
