# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Processing monitor page: live pipeline status for Seer Score.
Route: GET /monitor (local QA app only). Auto-refreshes every 30s.
"""
import json
import datetime
from pathlib import Path

BASE = Path(r'C:/Users/schof/veracity2')
DATA = BASE / 'data' / 'predictions.json'
WORKER_LOG = BASE / 'data' / 'miro_worker.log'
STATE_FILES = {
    'ts': BASE / 'data' / 'ts_state.json',
    'gate': BASE / 'data' / 'gate_state.json',
}


def gather():
    d = json.load(open(DATA, encoding='utf-8'))
    preds = d['predictions']
    live = [p for p in preds if not p.get('removed') and not p.get('gate_status')]
    per = {}
    for n in ['Peter Zeihan', 'Doomberg', 'Peter Diamandis', 'Ian Bremmer', 'David McAlvany']:
        xs = [p for p in live if p['individual_name'] == n]
        st = {'verdict': sum(1 for x in xs if x.get('verdict')),
              'almost': sum(1 for x in xs if not x.get('verdict') and len(x.get('judgements') or []) >= 2),
              'tbd': sum(1 for x in xs if not x.get('verdict') and len(x.get('judgements') or []) < 2)}
        per[n] = {'total': len(xs), **st}
    queues = {
        'mc_queued': sum(1 for x in preds if x.get('mc_status') == 'queued'),
        'mc_not_due': sum(1 for x in preds if x.get('mc_status') == 'not_due'),
        'mc_done': sum(1 for x in preds if x.get('mc_status') == 'done'),
        'miro_queued': sum(1 for x in preds if x.get('miro_status') == 'queued'),
        'miro_error': sum(1 for x in preds if x.get('miro_status') == 'error'),
        'miro_done': sum(1 for x in preds if x.get('miro_result') is not None),
    }
    marks = [x for x in preds if x.get('marty_verdict')]
    swarm_recent = [(x['individual_name'], x['claim'][:60], x.get('mc_result'))
                    for x in preds if x.get('mc_status') == 'done'][-6:]
    # Delphi scoring: per-mechanism stats (Delphi3080 = miro_*, DelphiCursor = delphicursor_*)
    miro_vals = [x['miro_result'] for x in preds if x.get('miro_result')]
    cur_vals = [x['delphicursor_result'] for x in preds if x.get('delphicursor_result')]
    def _mech(vals, field_conf='confidence'):
        confs = [v.get(field_conf) for v in vals if isinstance(v.get(field_conf), (int, float))]
        from collections import Counter
        votes = Counter(str((v.get('verdict') or v.get('vote') or '?')).lower()[:12] for v in vals)
        return {'count': len(vals), 'avg_confidence': round(sum(confs)/len(confs), 2) if confs else None,
                'votes': dict(votes)}
    delphi_scores = {
        'delphi3080': {'done': len(miro_vals),
                       'queued': sum(1 for x in preds if x.get('miro_status') == 'queued'),
                       'error': sum(1 for x in preds if x.get('miro_status') == 'error'),
                       **_mech(miro_vals)},
        'delphicursor': {'done': len(cur_vals),
                         'queued': sum(1 for x in preds if x.get('delphicursor_status') == 'queued'),
                         'error': sum(1 for x in preds if x.get('delphicursor_status') in ('error', 'failed_permanent')),
                         **_mech(cur_vals, 'confidence')},
    }
    cursor_recent = [(x['individual_name'], x['claim'][:60],
                      str((x.get('delphicursor_result') or {}).get('vote'))[:20])
                     for x in preds if x.get('delphicursor_result')][-6:]
    miro_recent = [(x['individual_name'], x['claim'][:60], str(x.get('miro_result', {}).get('verdict'))[:40])
                   for x in preds if x.get('miro_result')]
    log_tail = WORKER_LOG.read_text(encoding='utf-8').splitlines()[-8:] if WORKER_LOG.exists() else []
    # harvest jobs (Diamandis 2025-26, McAlvany 2025, ...)
    harvests = []
    for f in sorted(BASE.glob('data/harvest_*_state.json')):
        name = f.name.replace('harvest_', '').replace('_state.json', '')
        try:
            st = json.load(open(f, encoding='utf-8'))
            stats = st.get('stats', [])
            done_n = len(st.get('done', {}))
            total_added = sum(s.get('added', 0) for s in stats)
            last = stats[-1].get('date', '-') if stats else '-'
            active = 'yes' if (datetime.datetime.now() - datetime.datetime.fromtimestamp(f.stat().st_mtime)).total_seconds() < 120 else 'stalled?'
            harvests.append({'name': name, 'processed': done_n, 'added': total_added,
                             'last_date': last, 'active': active})
        except Exception:
            harvests.append({'name': name, 'processed': '?', 'added': '?', 'last_date': '?', 'active': '?'})
    smaug_version = json.load(open(BASE / 'data' / 'version.json', encoding='utf-8'))
    return {
        'now': datetime.datetime.now().strftime('%H:%M:%S'),
        'version': smaug_version.get('version'),
        'live_total': len(live),
        'per': per,
        'queues': queues,
        'marks': [(x['individual_name'], x['claim'][:50], x['marty_verdict']) for x in marks],
        'swarm_recent': swarm_recent,
        'miro_recent': miro_recent,
        'delphi_scores': delphi_scores,
        'cursor_recent': cursor_recent,
        'log_tail': log_tail,
        'harvests': harvests,
    }
