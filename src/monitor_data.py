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
    miro_recent = [(x['individual_name'], x['claim'][:60], str(x.get('miro_result', {}).get('verdict'))[:40])
                   for x in preds if x.get('miro_result')]
    log_tail = WORKER_LOG.read_text(encoding='utf-8').splitlines()[-8:] if WORKER_LOG.exists() else []
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
        'log_tail': log_tail,
    }
