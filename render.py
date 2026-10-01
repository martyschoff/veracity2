import json, os
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_FILE = BASE / 'data' / 'predictions.json'
TEMPLATES_DIR = BASE / 'templates'
OUT = BASE / 'surge_dist' / 'index.html'

with open(DATA_FILE, 'r', encoding='utf-8') as f:
    raw = json.load(f)

individuals = raw.get('individuals', [])
predictions = raw.get('predictions', [])

TRACKED_NAMES = ['Peter Zeihan', 'Doomberg', 'Peter Diamandis', 'Ian Bremmer']
tracked = [i for i in individuals if i.get('name') in TRACKED_NAMES]
tracked.sort(key=lambda i: TRACKED_NAMES.index(i['name']))
panelists = [i for i in individuals if i.get('name') not in TRACKED_NAMES]

for ind in tracked:
    ip = [p for p in predictions if p.get('individual_name') == ind['name']]
    ind['total_count'] = len(ip)
    ind['correct_count'] = len([p for p in ip if p.get('verdict') == 'correct'])
    ind['wrong_count'] = len([p for p in ip if p.get('verdict') == 'wrong'])

pbc = {}
for p in panelists:
    for cat in p.get('categories', []):
        pbc.setdefault(cat, []).append(p['name'])

tns = set(TRACKED_NAMES)
outstanding = [p for p in predictions if p.get('individual_name') in tns and p.get('verdict') is None]
outstanding.sort(key=lambda p: p.get('date', ''), reverse=True)

# Top 5 per person
rows_by_person = {}
for name in TRACKED_NAMES:
    person_preds = [p for p in outstanding if p.get('individual_name') == name]
    rows_by_person[name] = person_preds[:5]

# ALL predictions per person (for the full list view)
all_preds_by_person = {}
for name in TRACKED_NAMES:
    person_preds = [p for p in predictions if p.get('individual_name') == name]
    person_preds.sort(key=lambda p: p.get('date', ''), reverse=True)
    all_preds_by_person[name] = person_preds

total = len([p for p in predictions if p.get('individual_name') in tns])

CC = {'finance':'#10b981','energy':'#f59e0b','ukraine':'#3b82f6','china':'#ef4444','ai':'#8b5cf6','geopolitics':'#6366f1','other':'#6b7280'}

env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape(['html']))

def source_label(url):
    if not url:
        return 'Source'
    u = url.lower()
    if 'youtube.com' in u or 'youtu.be' in u:
        return 'YouTube'
    if 'newsletter.doomberg.com' in u:
        return 'Doomberg'
    if 'substack' in u:
        return 'Substack'
    if 'whitehouse.gov' in u:
        return 'White House'
    if 'twitter.com' in u or 'x.com' in u:
        return 'X'
    # fallback: domain name
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ''
    return host.replace('www.', '').split('.')[0].capitalize() if host else 'Source'

def condense(claim):
    """Condense a long claim into a headline-style sentence."""
    if not claim or len(claim) <= 120:
        return claim
    # Find a natural break point near 120 chars
    cutoff = claim[:140]
    # Try to end at a sentence boundary
    for sep in ['. ', '! ', '? ']:
        idx = cutoff.rfind(sep)
        if idx > 60:
            return claim[:idx + 1]
    # Try a comma
    idx = cutoff.rfind(', ')
    if idx > 60:
        return claim[:idx] + '…'
    # Hard cut at last space before 130
    idx = claim[:130].rfind(' ')
    if idx > 60:
        return claim[:idx] + '…'
    return claim[:120] + '…'

env.filters['source_label'] = source_label
env.filters['condense'] = condense
html = env.get_template('index.html').render(
    tracked_individuals=tracked, panelists=panelists, panelists_by_category=pbc,
    rows_by_person=rows_by_person, all_preds_by_person=all_preds_by_person,
    total_tracked_preds=total, category_colors=CC,
)

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'Wrote {len(html)} bytes to {OUT}')
for name, preds in rows_by_person.items():
    print(f'{name}: {len(preds)} rows')
    for r in preds:
        d = r.get('date','')
        c = r.get('category','')
        cl = str(r.get('claim',''))[:60]
        print(f'  {d} | {c} | {cl}')
