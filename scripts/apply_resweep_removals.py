"""Apply pending origin-resweep removals (data/qa_results.json verdict=remove)
to data/predictions.json; removed ones go to the guest pool with reasons."""
import json

BASE = r'C:/Users/schof/veracity2'
qa = json.load(open(f'{BASE}/data/qa_results.json', encoding='utf-8'))
d = json.load(open(f'{BASE}/data/predictions.json', encoding='utf-8'))
pool = json.load(open(f'{BASE}/data/guest_pool.json', encoding='utf-8'))

remove_ids = {v['id'] for v in qa.values() if v.get('verdict') == 'remove' and v.get('id')}
before = len(d['predictions'])
applied = 0
kept = []
for p in d['predictions']:
    if p['id'] in remove_ids:
        info = next(v for v in qa.values() if v.get('id') == p['id'])
        pool.append({
            'speaker': (info.get('speaker') or 'unattributed/third-party'),
            'claim': p['claim'], 'date': p['date'], 'source_url': p.get('source_url'),
            'note': f"origin resweep removal: {info.get('reason','')[:180]}",
            'removed_at': '2026-10-02'
        })
        applied += 1
    else:
        kept.append(p)
d['predictions'] = kept
json.dump(d, open(f'{BASE}/data/predictions.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
json.dump(pool, open(f'{BASE}/data/guest_pool.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
print(f'applied {applied} removals of {len(remove_ids)} flagged; {before} -> {len(kept)}; pool now {len(pool)}')
