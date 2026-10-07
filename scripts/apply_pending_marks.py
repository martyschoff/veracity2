# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Apply pending Marty marks (marks made while a sweep held a stale snapshot).
Runs at the end of a sweep chain, before swarm/miro pick them up.
"""
import json
import datetime
from pathlib import Path

BASE = Path(r'C:/Users/schof/veracity2')
DATA = BASE / 'data' / 'predictions.json'
PENDING = BASE / 'data' / 'pending_marks.json'

if not PENDING.exists():
    print('no pending marks')
    raise SystemExit(0)

pending = json.load(open(PENDING, encoding='utf-8'))
d = json.load(open(DATA, encoding='utf-8'))
byid = {p['id']: p for p in d['predictions']}
applied = 0
for pid, m in list(pending.items()):
    x = byid.get(pid)
    if not x:
        print('MISSING prediction:', pid)
        del pending[pid]
        continue
    x['marty_agrees'] = m['agrees']
    x['marty_note'] = m['note']
    x['marty_at'] = datetime.date.today().isoformat()
    if m.get('queue'):
        x['mc_status'] = 'queued'
        x['miro_status'] = 'queued'
    applied += 1
    del pending[pid]  # one-shot ledger
json.dump(d, open(DATA, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
PENDING.write_text(json.dumps(pending, indent=1), encoding='utf-8')
print(f'applied {applied} pending marks; ledger empty: {not pending}')
