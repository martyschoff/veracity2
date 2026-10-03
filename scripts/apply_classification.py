"""Apply Stage-A classification results: keep only PREDICTION; pool the rest; re-derive categories."""
import json, glob
from collections import Counter

BASE = r'C:/Users/schof/veracity2'
results = {}
for f in glob.glob(f'{BASE}/data/classify_state_*.json'):
    st = json.load(open(f, encoding='utf-8'))
    for k, v in st['results'].items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, dict) and vv.get('pred_id'):
                    results[vv['pred_id']] = vv
        elif isinstance(v, dict) and v.get('pred_id'):
            results[v['pred_id']] = v

d = json.load(open(f'{BASE}/data/predictions.json', encoding='utf-8'))
pool = json.load(open(f'{BASE}/data/guest_pool.json', encoding='utf-8'))

cls_counts = Counter()
kept, moved = [], 0
for p in d['predictions']:
    r = results.get(p['id'])
    if not r:
        kept.append(p)  # unclassified: keep, flagged for stage B
        continue
    c = r.get('class', 'UNCLEAR').upper()
    cls_counts[c] += 1
    if c == 'PREDICTION':
        if r.get('category'):
            p['category'] = r['category']
        kept.append(p)
    else:
        pool.append({
            'speaker': p['individual_name'],
            'claim': p['claim'], 'date': p['date'], 'source_url': p.get('source_url'),
            'class': c, 'reason': (r.get('reason') or '')[:200],
            'removed_at': '2026-10-03'
        })
        moved += 1

json.dump(d, open(f'{BASE}/data/predictions.json','w',encoding='utf-8'), indent=2, ensure_ascii=False)
json.dump(pool, open(f'{BASE}/data/guest_pool.json','w',encoding='utf-8'), indent=2, ensure_ascii=False)
print('class counts:', dict(cls_counts))
print(f'kept {len(kept)}, moved {moved} to pool (pool now {len(pool)})')
per = Counter(p['individual_name'] for p in kept if p['individual_name'] in
              ('Peter Zeihan','Doomberg','Peter Diamandis','Ian Bremmer','David McAlvany'))
print('tracked now:', dict(per))