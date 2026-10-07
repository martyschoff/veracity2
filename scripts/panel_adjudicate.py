"""Weighted panel adjudication: run panelist votes over a target set of
predictions using the 4-GPU qwen3:8b pool (nimo as escalation).

  python scripts/panel_adjudicate.py --person Doomberg --year 2024
"""
import argparse, json, random, re, subprocess, time
from pathlib import Path

BASE = Path(r'C:/Users/schof/veracity2')
POOL = ['http://100.84.167.88:11434']  # nimo 32b: judgment gold standard
UPPOOL = ['http://100.120.21.39:11434']  # upthread64 llama3.1:8b: 100% decisive in 10-claim test
NIMO = 'http://100.84.167.88:11434'
MODEL = 'qwen3:32b'  # 8b pool proved too shallow: votes unclear on everything (2026-10-06)

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--person', required=True)
    ap.add_argument('--year', default=None)
    ap.add_argument('--force', action='store_true', help='re-adjudicate: clear existing unclear-heavy votes')
    args = ap.parse_args()

    d = json.load(open(BASE / 'data' / 'predictions.json', encoding='utf-8'))
    NON_VOTERS = {'FactCheck.org', 'AP Fact Check', 'Google Fact Check Explorer', 'Wall Street Journal',
                  'NHK World', 'Warsaw Voice', 'Notes from Poland', 'Jerusalem Post', 'UnHerd',
                  'Bloomberg Surveillance', 'Miles Franklin', 'MiroFish'}
    ind_w = {i['name']: i.get('panel_weight', 1.0) for i in d['individuals'] if i['name'] not in NON_VOTERS}
    import datetime
    today = datetime.date.today().isoformat()
    def due(p):
        if p.get('test_eligible_at'):
            return p['test_eligible_at'] <= today
        m = re.search(r'\b(20[2-9]\d)\b', p.get('claim', ''))
        return not m or m.group(1) <= today[:4]
    if args.force:
        cleared = 0
        for p in d['predictions']:
            if p['individual_name'] == args.person and (p.get('judgements') or []) and not p.get('verdict'):
                unc = sum(1 for v in p['judgements'] if v['verdict'] == 'unclear')
                if unc >= len(p['judgements']) - 1:  # all/most unclear = garbage run
                    p['judgements'] = []
                    cleared += 1
        json.dump(d, open(BASE / 'data' / 'predictions.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
        print(f'force: cleared {cleared} unclear-heavy prediction vote sets', flush=True)
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
        if p.get('judgements') and len(p['judgements']) >= 2:
            continue
        # pick 3 weighted panelists (dedupe, avoid the claimant)
        pool_names = [n for n in ind_w if n != args.person]
        panelists = random.sample(pool_names, min(3, len(pool_names)))
        votes = list(p.get('judgements') or [])
        existing = {v['panelist'] for v in votes}
        for name in panelists:
            if f'{name} (simulated)' in existing:
                continue
            w = ind_w.get(name, 1.0)
            prompt = PROMPT.format(name=name, role=ROLES.get(w, 'energy specialist'),
                                   weight=w, date=p.get('date', ''), claim=p['claim'][:600],
                                   excerpt=(p.get('transcript_excerpt') or '')[:800])
            res = ask(POOL[port_i % len(POOL)], prompt)
            port_i += 1
            if res is None:  # escalate to nimo
                res = ask(NIMO, prompt)
            if res is None:
                continue
            votes.append({'panelist': f'{name} (simulated)', 'verdict': res.get('vote', 'unclear'),
                          'weight': w, 'reasoning': (res.get('reasoning') or '')[:300]})
        p['judgements'] = votes
        # weighted tally: correct=+w, incorrect=-w, unclear=0; verdict if |sum| >= 2.0
        score = sum(v['weight'] * (1 if v['verdict'] == 'correct' else -1 if v['verdict'] == 'incorrect' else 0)
                    for v in votes)
        if score >= 2.0:
            p['verdict'] = 'correct'
        elif score <= -2.0:
            p['verdict'] = 'wrong'
        json.dump(d, open(BASE / 'data' / 'predictions.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)  # save every prediction
        print(f'{pi + 1}/{len(targets)} done | votes={len(votes)} score={round(score, 2)} verdict={p.get("verdict")}', flush=True)
    json.dump(d, open(BASE / 'data' / 'predictions.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
    print('ADJUDICATION_DONE', flush=True)


if __name__ == '__main__':
    main()
