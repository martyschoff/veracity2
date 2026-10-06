"""Apply gate results: pull prescriptions/facts into the implicit queue."""
import json
from pathlib import Path
from collections import Counter

BASE = Path(r'C:/Users/schof/veracity2')
d = json.load(open(BASE / 'data' / 'predictions.json', encoding='utf-8'))
byid = {p['id']: p for p in d['predictions']}
q = json.load(open(BASE / 'data' / 'implicit_queue.json', encoding='utf-8')) if (BASE / 'data' / 'implicit_queue.json').exists() else []
qids = {e['id'] for e in q}
counts = Counter()
for k in range(4):
    f = BASE / 'data' / f'gate_results_{k}.json'
    if not f.exists():
        continue
    for e in json.load(open(f, encoding='utf-8')):
        counts[e.get('type')] += 1
        p = byid.get(e['id'])
        if not p or p.get('gate_status'):
            continue
        if e.get('type') in ('prescription', 'fact'):
            p['gate_status'] = 'queued'
            if e['id'] not in qids:
                q.append({
                    'id': p['id'], 'individual_name': p['individual_name'],
                    'date': p.get('date', ''), 'claim': p['claim'],
                    'implicit_forecast': e.get('implicit_forecast'),
                    'gate_type': e['type'], 'reason': e.get('reason', ''),
                    'source_url': p.get('source_url', ''), 't_seconds': p.get('t_seconds'),
                    'status': 'pending',
                })
                qids.add(e['id'])
json.dump(d, open(BASE / 'data' / 'predictions.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
(BASE / 'data' / 'implicit_queue.json').write_text(json.dumps(q, indent=2), encoding='utf-8')
print('gate types:', dict(counts))
print('queue size:', len(q), '| gated predictions:', sum(1 for p in d['predictions'] if p.get('gate_status') == 'queued'))
