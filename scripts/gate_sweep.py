"""Gate sweep: classify existing live predictions, pull non-predictions into
the implicit review queue. Sharded + resumable.

  python scripts/gate_sweep.py --shard 0 --stride 4
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claim_gate import classify

BASE = Path(r'C:/Users/schof/veracity2')
QUEUE = BASE / 'data' / 'implicit_queue.json'
STATE = BASE / 'data' / 'gate_state.json'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--shard', type=int, required=True)
    ap.add_argument('--stride', type=int, default=4)
    args = ap.parse_args()

    st = json.load(open(STATE, encoding='utf-8')) if STATE.exists() else {}
    d = json.load(open(BASE / 'data' / 'predictions.json', encoding='utf-8'))
    preds = [p for p in d['predictions'] if not p.get('gate_status') and not p.get('removed')]
    todo = preds[args.shard::args.stride]
    print(f'shard {args.shard}: {len(todo)} to classify', flush=True)

    q = json.load(open(QUEUE, encoding='utf-8')) if QUEUE.exists() else []

    for i, p in enumerate(todo):
        if p['id'] in st:
            continue
        res = classify(p['claim'], p.get('transcript_excerpt') or '')
        st[p['id']] = res.get('type', 'unknown')
        if res.get('type') in ('prescription', 'fact') and p['individual_name']:
            p['gate_status'] = 'queued'
            q.append({
                'id': p['id'],
                'individual_name': p['individual_name'],
                'date': p.get('date', ''),
                'claim': p['claim'],
                'implicit_forecast': res.get('implicit_forecast'),
                'gate_type': res['type'],
                'reason': res.get('reason', ''),
                'source_url': p.get('source_url', ''),
                't_seconds': p.get('t_seconds'),
                'status': 'pending',
            })
        if (i + 1) % 5 == 0:
            STATE.write_text(json.dumps(st), encoding='utf-8')
            json.dump(d, open(BASE / 'data' / 'predictions.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
            QUEUE.write_text(json.dumps(q, indent=2), encoding='utf-8')
            print(f'{i + 1}/{len(todo)} classified, queued so far: {len(q)}', flush=True)

    STATE.write_text(json.dumps(st), encoding='utf-8')
    json.dump(d, open(BASE / 'data' / 'predictions.json', 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
    QUEUE.write_text(json.dumps(q, indent=2), encoding='utf-8')
    from collections import Counter
    print(f'GATE_SHARD_DONE {args.shard}:', dict(Counter(st.values())), flush=True)


if __name__ == '__main__':
    main()
