# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
import json, os, math
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

def wilson_confidence_interval(correct, total, confidence=0.95):
    """Calculate Wilson score confidence interval for proportion."""
    if total == 0:
        return (0.0, 0.0)
    if total == 1:
        # Special case for N=1
        return (0.0, 1.0) if correct == 1 else (0.0, 0.0)
    
    p = correct / total
    z = 1.96 if confidence == 0.95 else 2.576  # 95% or 99%
    
    denominator = 1 + z**2 / total
    centre_adjusted_probability = (p + z**2 / (2 * total)) / denominator
    adjusted_standard_deviation = math.sqrt(max(0, (p * (1 - p) + z**2 / (4 * total)) / total)) / denominator
    
    lower = centre_adjusted_probability - z * adjusted_standard_deviation
    upper = centre_adjusted_probability + z * adjusted_standard_deviation
    
    return (max(0.0, lower), min(1.0, upper))

def compute_panel_probability(judgements):
    """Compute P_panel per claim from judgements."""
    if not judgements:
        return None
        
    correct_weight = sum(j.get('weight', 1.0) for j in judgements if j.get('verdict') == 'correct')
    total_weight = sum(j.get('weight', 1.0) for j in judgements if j.get('verdict') in ['correct', 'wrong', 'incorrect'])
    
    if total_weight == 0:
        return None
    
    return correct_weight / total_weight

def compute_person_scores(predictions, person_name):
    """Compute accuracy and Brier scores for a person."""
    # Filter to resolved claims for this person
    person_preds = [p for p in predictions if p.get('individual_name') == person_name]
    resolved_preds = [p for p in person_preds if p.get('verdict') in ['correct', 'wrong', 'incorrect']]
    
    if not resolved_preds:
        return {
            'accuracy': None, 'accuracy_ci': None, 'n_resolved': 0,
            'brier_shrunk': None, 'brier_raw': None, 'skill': None,
            'base_rate': None, 'display_scores': len(resolved_preds) >= 10
        }
    
    # Compute accuracy
    correct_count = sum(1 for p in resolved_preds if p.get('verdict') == 'correct')
    accuracy = correct_count / len(resolved_preds)
    lower, upper = wilson_confidence_interval(correct_count, len(resolved_preds))
    
    # Compute base rate (person's overall fraction correct)
    base_rate = accuracy
    
    # Compute Brier scores ONLY against INDEPENDENT outcomes (Marty final marks or
    # authoritative fact-checks). Panel-resolved claims are circular: the panel voted
    # the verdict, so Brier would measure the panel agreeing with itself (0.00-0.01).
    brier_claims = []
    for pred in person_preds:
        is_independent = (pred.get('marty_verdict') in ('correct', 'wrong')
                          or pred.get('verdict_source') == 'authoritative')
        if not is_independent:
            continue
        judgements = pred.get('judgements', [])
        p_panel = compute_panel_probability(judgements)
        if p_panel is None:  # Only include claims with decisive votes
            continue
        truth = pred.get('marty_verdict') or pred.get('verdict')
        # Shrinkage: P_adjusted = 0.7 * P_panel + 0.3 * base_rate
        p_adjusted = 0.7 * p_panel + 0.3 * base_rate
        outcome = 1.0 if truth == 'correct' else 0.0

        brier_shrunk = (p_adjusted - outcome) ** 2
        brier_raw = (p_panel - outcome) ** 2

        brier_claims.append({
            'brier_shrunk': brier_shrunk,
            'brier_raw': brier_raw,
            'outcome': outcome
        })
    
    if brier_claims:
        avg_brier_shrunk = sum(c['brier_shrunk'] for c in brier_claims) / len(brier_claims)
        avg_brier_raw = sum(c['brier_raw'] for c in brier_claims) / len(brier_claims)
        # Base rate Brier score (Brier score of always predicting base_rate)
        base_rate_brier = base_rate * (1 - base_rate)  
        skill = base_rate_brier - avg_brier_shrunk
    else:
        avg_brier_shrunk = avg_brier_raw = skill = None
        
    return {
        'accuracy': accuracy,
        'accuracy_ci': (lower, upper),
        'n_resolved': len(resolved_preds),
        'n_brier': len(brier_claims),
        'brier_shrunk': avg_brier_shrunk,
        'brier_raw': avg_brier_raw,
        'skill': skill,
        'base_rate': base_rate,
        'display_scores': len(brier_claims) >= 10,  # Brier needs independent-truth N>=10
    }

# Clear debug files
with open(BASE / 'debug_scores.txt', 'w', encoding='utf-8') as f:
    f.write("Debug scores log:\n")

TRACKED_NAMES = ['Peter Zeihan', 'Doomberg', 'Peter Diamandis', 'Ian Bremmer', 'David McAlvany']
tracked = [i for i in individuals if i.get('name') in TRACKED_NAMES]
tracked.sort(key=lambda i: TRACKED_NAMES.index(i['name']))
panelists = [i for i in individuals if i.get('name') not in TRACKED_NAMES]

for ind in tracked:
    ip = [p for p in predictions if p.get('individual_name') == ind['name']]
    ind['total_count'] = len(ip)
    ind['correct_count'] = len([p for p in ip if p.get('verdict') == 'correct'])
    ind['wrong_count'] = len([p for p in ip if p.get('verdict') in ['wrong', 'incorrect']])
    
    # Compute scoring metrics
    scores = compute_person_scores(predictions, ind['name'])
    ind['scores'] = scores
    
    # Debug output
    with open(BASE / 'debug_scores.txt', 'a', encoding='utf-8') as debug_f:
        debug_f.write(f"{ind['name']}: {scores}\n")

# Compute scores for any other person with N>=1 resolved claims
other_people_with_scores = []
all_person_names = set(p.get('individual_name') for p in predictions if p.get('individual_name'))
for person_name in all_person_names:
    if person_name not in TRACKED_NAMES:
        scores = compute_person_scores(predictions, person_name)
        if scores['n_resolved'] >= 1:
            other_people_with_scores.append({
                'name': person_name,
                'scores': scores
            })

# Compute global panel skill score
def compute_global_panel_skill(predictions):
    """Compute overall panel skill across all resolved predictions."""
    all_resolved = [p for p in predictions if p.get('verdict') in ['correct', 'wrong', 'incorrect']]
    
    if not all_resolved:
        return None
        
    # Overall base rate (fraction of all predictions that were correct)
    overall_correct = sum(1 for p in all_resolved if p.get('verdict') == 'correct')
    base_rate = overall_correct / len(all_resolved)
    
    # Collect all panel predictions
    panel_predictions = []
    for pred in all_resolved:
        judgements = pred.get('judgements', [])
        p_panel = compute_panel_probability(judgements)
        if p_panel is not None:
            outcome = 1.0 if pred.get('verdict') == 'correct' else 0.0
            p_adjusted = 0.7 * p_panel + 0.3 * base_rate
            brier_score = (p_adjusted - outcome) ** 2
            panel_predictions.append(brier_score)
    
    if panel_predictions:
        avg_brier = sum(panel_predictions) / len(panel_predictions)
        base_rate_brier = base_rate * (1 - base_rate)
        skill = base_rate_brier - avg_brier
        return {
            'brier': avg_brier,
            'skill': skill,
            'n_predictions': len(panel_predictions),
            'base_rate': base_rate
        }
    return None

global_panel_skill = compute_global_panel_skill(predictions)

pbc = {}
for p in panelists:
    w = p.get('panel_weight', 1.0)
    for cat in p.get('categories', []):
        pbc.setdefault(cat, []).append({'name': p['name'], 'w': w})
for cat in pbc:
    pbc[cat].sort(key=lambda e: -e['w'])

tns = set(TRACKED_NAMES)
outstanding = [p for p in predictions if p.get('individual_name') in tns and p.get('verdict') is None and not p.get('gate_status')]
outstanding.sort(key=lambda p: p.get('date', ''), reverse=True)

# ALL predictions per person for the grid (JS handles top-5 + filtering)
def _deeplink(p):
    u = p.get('source_url') or ''
    t = p.get('t_seconds')
    if t is not None and 'youtube.com' in u and 't=' not in u:
        u += ('&' if '?' in u else '?') + 't=' + str(max(0, int(t) - 15))  # 15s of lead-in context
    elif t is None and '#' not in u and not u.lower().startswith('mailto'):
        # articles: scroll-to-text fragment anchored on the excerpt
        anchor_src = (p.get('transcript_excerpt') or p.get('claim') or '')
        words = [w for w in anchor_src.split() if w][:10]
        if len(words) >= 4:
            u += '#:~:text=' + '%20'.join(words)
    return u

# Delphi3080 hover tooltip: <=50 words distilled from the sim rationale
def _miro_tip(p):
    m = p.get('miro_result') or {}
    txt = (m.get('summary') or m.get('rationale') or '').strip()
    if not txt:
        return None
    return ' '.join(txt.split()[:50])
def _cursor_tip(p):
    m = p.get('delphicursor_result') or {}
    txt = (m.get('reasoning') or m.get('summary') or '').strip()
    if not txt:
        return None
    return ' '.join(txt.split()[:50])
for p in predictions:
    _t = _miro_tip(p)
    if _t:
        p['miro_tooltip'] = _t
    _c = _cursor_tip(p)
    if _c:
        p['cursor_tooltip'] = _c

rows_by_person = {}
for name in TRACKED_NAMES:
    # grid columns show ALL tracked predictions (verdicted included) - verdict
    # boxes (Marty final / panel) render per template; outstanding-only hid
    # graded entries entirely.
    person_preds = [p for p in predictions if p.get('individual_name') == name]
    person_preds.sort(key=lambda p: p.get('date', ''), reverse=True)
    for p in person_preds:
        p['source_url'] = _deeplink(p)
    rows_by_person[name] = person_preds

# ALL predictions per person (for the full list view)
all_preds_by_person = {}
for name in TRACKED_NAMES:
    person_preds = [p for p in predictions if p.get('individual_name') == name]
    person_preds.sort(key=lambda p: p.get('date', ''), reverse=True)
    for p in person_preds:
        p['source_url'] = _deeplink(p)
    all_preds_by_person[name] = person_preds

total = len([p for p in predictions if p.get('individual_name') in tns])

# version: +0.01 per pass
_vf = BASE / 'data' / 'version.json'
_ver = json.load(open(_vf, encoding='utf-8'))
VERSION = round(_ver['version'] + 0.01, 2)
_ver['version'] = VERSION
json.dump(_ver, open(_vf, 'w', encoding='utf-8'), indent=1)

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
# Debug: write individuals data structure
with open(BASE / 'debug_individuals.txt', 'w', encoding='utf-8') as debug_f:
    for ind in tracked:
        debug_f.write(f"Individual: {ind['name']}\n")
        debug_f.write(f"  scores key exists: {'scores' in ind}\n")
        if 'scores' in ind:
            debug_f.write(f"  scores: {ind['scores']}\n")
        debug_f.write("\n")

html = env.get_template('index.html').render(
    tracked_individuals=tracked, panelists=panelists, panelists_by_category=pbc,
    app_version=VERSION, rows_by_person=rows_by_person, all_preds_by_person=all_preds_by_person,
    total_tracked_preds=total, category_colors=CC,
    other_people_with_scores=other_people_with_scores, global_panel_skill=global_panel_skill,
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

# publish version.json for the static site (fetches /version.json at runtime)
import os as _os, shutil as _shutil
_shutil.copy(str(BASE / 'data' / 'version.json'), _os.path.join(_os.path.dirname(OUT), 'version.json'))
