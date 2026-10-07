# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Quarterly panelist calibration (Tetlock-style), run as a SEPARATE review process.

For a given quarter (e.g. 2024Q1): score each panelist's votes against the final
verdicts of predictions made that quarter, propose tier moves (up/down), and write
a PROPOSAL for the owner to approve or reject. Nothing is auto-applied.

Rules:
  - needs >= MIN_VOTES decided votes in the quarter to make a proposal
  - accuracy >= UP_THRESHOLD (default 0.75) -> propose one tier up
  - accuracy <= DOWN_THRESHOLD (default 0.40) -> propose one tier down
  - else -> keep (a bad quarter is survivable; correction is expected)

Usage: python scripts/quarterly_calibration.py --quarter 2024Q1
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

BASE = Path(r'C:/Users/schof/veracity2')
OUT = BASE / 'data' / 'calibration'

TIERS = [1.0, 1.25, 1.5]
MIN_VOTES = 8
UP_THRESHOLD = 0.75
DOWN_THRESHOLD = 0.40


def quarter_bounds(q):
    year, n = q.split('Q')
    year = int(year)
    start = f'{year}-{(int(n)-1)*3+1:02d}-01'
    end = f'{year}-{int(n)*3:02d}-31'
    return start, end


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quarter', required=True, help='e.g. 2024Q1')
    args = ap.parse_args()
    start, end = quarter_bounds(args.quarter)

    d = json.load(open(BASE / 'data' / 'predictions.json', encoding='utf-8'))
    score = defaultdict(lambda: {'correct': 0, 'total': 0, 'weight': None})
    decided_preds = 0
    for p in d['predictions']:
        if p.get('removed') or p.get('gate_status'):
            continue
        if not (start <= p.get('date', '') <= end):
            continue
        v = p.get('verdict')
        if v not in ('correct', 'wrong'):
            continue
        decided_preds += 1
        for j in p.get('judgements', []):
            if j.get('verdict') not in ('correct', 'incorrect'):
                continue  # unclear votes don't count for/against
            name = j['panelist'].replace(' (simulated)', '')
            s = score[name]
            s['total'] += 1
            hit = (j['verdict'] == v)
            s['correct'] += int(hit)
            s['weight'] = j.get('weight', s['weight'])

    proposals = []
    for name, s in sorted(score.items(), key=lambda kv: -kv[1]['total']):
        if s['total'] < MIN_VOTES:
            continue
        acc = s['correct'] / s['total']
        w = s['weight'] or 1.0
        tier_idx = TIERS.index(w) if w in TIERS else 0
        if acc >= UP_THRESHOLD and tier_idx < len(TIERS) - 1:
            action = f'UP {w} -> {TIERS[tier_idx+1]}'
        elif acc <= DOWN_THRESHOLD and tier_idx > 0:
            action = f'DOWN {w} -> {TIERS[tier_idx-1]}'
        else:
            action = 'keep'
        proposals.append({'panelist': name, 'votes': s['total'], 'accuracy': round(acc, 2),
                          'current_weight': w, 'action': action})

    OUT.mkdir(exist_ok=True)
    report = {
        'quarter': args.quarter,
        'decided_predictions': decided_preds,
        'scoring_panelists': len(score),
        'proposals': proposals,
        'status': 'PROPOSED - awaiting owner approval',
        'rules': {'min_votes': MIN_VOTES, 'up': UP_THRESHOLD, 'down': DOWN_THRESHOLD},
    }
    out = OUT / f'{args.quarter}_proposal.json'
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')

    lines = [f"# Quarterly Calibration Proposal — {args.quarter}",
             f"Decided predictions: {decided_preds} | panelists scored: {len(score)} | "
             f"min votes for a move: {MIN_VOTES} | up >= {UP_THRESHOLD:.0%} | down <= {DOWN_THRESHOLD:.0%}", "",
             "| Panelist | Votes | Accuracy | Weight | Proposal |", "|---|---|---|---|---|"]
    for pr in proposals:
        lines.append(f"| {pr['panelist']} | {pr['votes']} | {pr['accuracy']:.0%} | {pr['current_weight']}x | {pr['action']} |")
    insuff = [n for n, s in score.items() if s['total'] < MIN_VOTES]
    if insuff:
        lines.append(f"\nInsufficient sample (no proposal): {', '.join(sorted(insuff))}")
    md = OUT / f'{args.quarter}_proposal.md'
    md.write_text('\n'.join(lines), encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
