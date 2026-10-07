# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
import json, time, re
DATA = r"C:/Users/schof/veracity2/data/predictions.json"

def load(p): return json.load(open(p, encoding='utf-8'))

d = load(DATA)
wc = load(r"C:/Users/schof/veracity2/data/mcalvany_wc_extractions.json")
yt = load(r"C:/Users/schof/veracity2/data/mcalvany_yt_extractions.json")
existing_urls = {p['source_url'] for p in d['predictions']}
existing_claims = {p['claim'][:80] for p in d['predictions']}
ts = int(time.time())
n = 0
for batch in wc + yt:
    url = batch['url']
    for pred in batch['predictions']:
        claim = ' '.join(pred['claim'].split())
        if not claim or url in existing_urls and False:
            continue
        if claim[:80] in existing_claims:
            continue
        if re.search(r'\b(20\d\d)\b', claim):
            yrs = [int(y) for y in re.findall(r'\b(20\d\d)\b', claim)]
            if all(y <= int(batch['date'][:4]) for y in yrs) and not re.search(r'\b(20\d\d)\b.*ahead|coming|next', claim):
                pass  # keep; year filter already applied at extraction
        d['predictions'].append({
            'id': f'pred_{ts}_{n}',
            'individual_name': 'David McAlvany',
            'date': batch['date'],
            'category': 'finance',
            'claim': claim,
            'source_url': url,
            'transcript_excerpt': pred.get('excerpt', ''),
            'verdict': None,
            'measurement_type': pred.get('measurement_type', 'subjective'),
            'test_status': 'eligible',
            'testing_since': time.strftime('%Y-%m-%d'),
            'judgements': [],
        })
        existing_claims.add(claim[:80])
        n += 1
json.dump(d, open(DATA, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
print('added', n, 'total mcalvany preds:', sum(1 for p in d['predictions'] if p['individual_name'] == 'David McAlvany'))
