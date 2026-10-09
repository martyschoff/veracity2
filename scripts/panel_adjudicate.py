# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Weighted panel adjudication: run panelist votes over a target set of
predictions using the 4-GPU qwen3:8b pool (nimo as escalation).

  python scripts/panel_adjudicate.py --person Doomberg --year 2024
"""
import argparse, json, random, re, subprocess, time
from pathlib import Path
import sys, os as _os
_os.sys.path if False else None
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from data_lock import locked_data
from src.brier import record_probabilities, finalize_brier

import filelock

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / 'data' / 'predictions.json'
LOCK = BASE / 'data' / 'predictions.json.lock'
POOL = ['http://100.84.167.88:11434']  # nimo 32b: judgment gold standard
UPPOOL = ['http://100.120.21.39:11434']  # upthread64 llama3.1:8b: 100% decisive in 10-claim test
NIMO = 'http://100.84.167.88:11434'
MODEL = 'qwen3:32b'  # 8b pool proved too shallow: votes unclear on everything (2026-10-06)

# Non-voting entities (fact-checkers, bots, etc.)
NON_VOTERS = {'Fact-Check', 'Twitter Bot', 'Publication Account'}

PROMPT = """You are simulating panelist {name} ({role}) — weight {weight}x — on a predictions adjudication panel.

PREDICTION (made {date}): {claim}
TRANSCRIPT CONTEXT: {excerpt}

It is now late 2026. Judge ONLY whether the prediction has been proven correct, incorrect, or is not yet decidable by this date.
RULES: "correct" = the event happened or, if its target date is still future, current evidence clearly shows it on track. "incorrect" = the event failed, is clearly off track, or its deadline passed unmet. "unclear" = you genuinely have no basis to judge the trajectory either way. Do not default to "unclear" out of caution - if you know the subject, commit to a judgment.
Answer STRICTLY as JSON: {{"vote": "correct"|"incorrect"|"unclear", "reasoning": "1-2 sentences"}}"""

ROLES = {
    1.5: 'professional energy forecaster, institutional analyst',
    1.25: 'independent energy analyst',
    1.0: 'energy specialist',
}


def ask(port, prompt):
    body = json.dumps({'model': MODEL, 'stream': False, 'think': False,
                       'messages': [{'role': 'user', 'content': prompt}],
                       'options': {'num_predict': 300, 'num_ctx': 32768, 'temperature': 0.3}})
    r = subprocess.run(['curl', '-s', '-m', '120', f'{port}/api/chat', '-d', body],
                       capture_output=True, text=True, timeout=140)
    try:
        c = json.loads(r.stdout)['message']['content']
        import re
        m = re.search(r'\{.*\}', c, re.S)
        return json.loads(m.group(0))
    except Exception:
        return None


def due(prediction: dict) -> bool:
    """Check if prediction is due for adjudication."""
    import datetime
    today = datetime.date.today().isoformat()
    due_date = prediction.get("test_eligible_at")
    if due_date:
        return due_date <= today
    
    # Extract year from claim if no explicit due date
    import re
    year_match = re.search(r'\b(20[2-9]\d)\b', prediction.get('claim', ''))
    if year_match:
        year = int(year_match.group(1))
        current_year = datetime.date.today().year
        return year <= current_year
    
    # Default to due if no date information
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--person', required=True)
    ap.add_argument('--year', default=None)
    ap.add_argument('--force', action='store_true', help='re-adjudicate: clear existing unclear-heavy votes')
    args = ap.parse_args()

    # Load + force clear + build target list — all under one lock
    with filelock.FileLock(str(LOCK), timeout=300):
        with open(DATA, encoding='utf-8') as f:
            d = json.load(f)
        if args.force:
            cleared = 0
            for p in d['predictions']:
                if p['individual_name'] == args.person and (p.get('judgements') or []) and not p.get('verdict'):
                    unc = sum(1 for v in p['judgements'] if v['verdict'] == 'unclear')
                    if unc >= len(p['judgements']) - 1:  # all/most unclear = garbage run
                        p['judgements'] = []
                        cleared += 1
            with locked_data() as fresh:
                fidx = {q['id']: i2 for i2, q in enumerate(fresh['predictions'])}
                for p in d['predictions']:
                    if p['id'] in fidx:
                        fresh['predictions'][fidx[p['id']]] = p
            print(f'force: cleared {cleared} unclear-heavy prediction vote sets', flush=True)
        ind_w = {i['name']: i.get('panel_weight', 1.0) for i in d['individuals'] if i['name'] not in NON_VOTERS}
        targets = [p for p in d['predictions']
                   if p['individual_name'] == args.person and not p.get('removed')
                   and not p.get('gate_status') and due(p)
                   and (args.year is None or p.get('date', '').startswith(args.year))]
        skipped = sum(1 for p in d['predictions'] if p['individual_name'] == args.person
                      and not p.get('removed') and not p.get('gate_status') and not due(p))

    if skipped:
        print(f'{skipped} not-yet-due predictions skipped', flush=True)
    print(f'{len(targets)} predictions to adjudicate', flush=True)

    port_i = 0
    for pi, p in enumerate(targets):
        pred_id = p.get('id')
        if p.get('judgements') and len(p['judgements']) >= 2:
            continue

        pool_names = [n for n in ind_w if n != args.person]
        panelists = random.sample(pool_names, min(3, len(pool_names)))

        # ---- LLM voting runs outside lock (saves ~seconds per prediction) ----
        new_votes = []
        for name in panelists:
            w = ind_w.get(name, 1.0)
            prompt = PROMPT.format(name=name, role=ROLES.get(w, 'energy specialist'),
                                   weight=w, date=p.get('date', ''), claim=p['claim'][:600],
                                   excerpt=(p.get('transcript_excerpt') or '')[:800])
            res = ask(POOL[port_i % len(POOL)], prompt)
            port_i += 1
            if res is None:
                res = ask(NIMO, prompt)
            if res is None:
                continue
            new_votes.append({'panelist': f'{name} (simulated)', 'verdict': res.get('vote', 'unclear'),
                              'weight': w, 'reasoning': (res.get('reasoning') or '')[:300]})

        if not new_votes:
            print(f'{pi + 1}/{len(targets)} skipped (no votes)', flush=True)
            continue

        # ---- Acquire lock, reload fresh data, apply new votes, save ----
        with filelock.FileLock(str(LOCK), timeout=300):
            with open(DATA, encoding='utf-8') as f:
                d = json.load(f)
            target = next((x for x in d['predictions'] if x.get('id') == pred_id), None)
            if not target:
                print(f'{pi + 1}/{len(targets)} TARGET GONE', flush=True)
                continue

            existing_votes = list(target.get('judgements') or [])
            existing_panelists = {v['panelist'] for v in existing_votes}
            for v in new_votes:
                if v['panelist'] not in existing_panelists:
                    existing_votes.append(v)
            target['judgements'] = existing_votes

            score = sum(v['weight'] * (1 if v['verdict'] == 'correct' else -1 if v['verdict'] == 'incorrect' else 0)
                        for v in existing_votes)
            verdict_reached = False
            if score >= 2.0:
                target['verdict'] = 'correct'
                verdict_reached = True
            elif score <= -2.0:
                target['verdict'] = 'wrong'
                verdict_reached = True
            
            # Compute panel weighted probability for Brier ledger
            total_weight = sum(v['weight'] for v in existing_votes if v['verdict'] in ('correct', 'incorrect', 'unclear'))
            if total_weight > 0:
                weighted_prob = sum(
                    v['weight'] * (1.0 if v['verdict'] == 'correct' else 0.0 if v['verdict'] == 'incorrect' else 0.5)
                    for v in existing_votes
                ) / total_weight
                target.setdefault('_panel_prob', round(weighted_prob, 4))

            with locked_data() as fresh:
                fidx = {q['id']: i3 for i3, q in enumerate(fresh['predictions'])}
                fresh['predictions'][fidx[target['id']]] = target  # merge only OUR change
        
        # Record panel probability in Brier ledger (outside the lock to avoid nested locking)
        panel_prob = target.get('_panel_prob')
        if panel_prob is not None:
            record_probabilities(pred_id, {"panel_weighted": panel_prob})
        
        # Finalize Brier scores if verdict was reached
        if verdict_reached:
            outcome = 1 if target['verdict'] == 'correct' else 0
            finalize_brier(pred_id, outcome)

        print(f'{pi + 1}/{len(targets)} done | votes={len(existing_votes)} score={round(score, 2)} verdict={target.get("verdict")}', flush=True)

    # Final write: overlay our targets into the latest on-disk state
    with locked_data() as fresh:
        fidx = {q['id']: i3 for i3, q in enumerate(fresh['predictions'])}
        for t2 in targets:
            if t2['id'] in fidx:
                fresh['predictions'][fidx[t2['id']]] = t2
    print('ADJUDICATION_DONE', flush=True)


if __name__ == '__main__':
    main()
