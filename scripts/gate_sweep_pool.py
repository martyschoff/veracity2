# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Gate sweep using the 4-GPU qwen3:8b pool on big3080.
Classifies claims; writes per-shard results (no shared-file writes).
  python scripts/gate_sweep_pool.py --shard 0 --stride 4 --port 11435
"""
import argparse, json, re, subprocess, sys
from pathlib import Path

BASE = Path(r'C:/Users/schof/veracity2')
HOST = 'http://100.124.236.23'
MODEL = 'qwen3:8b'

PROMPT = """Classify this claim made by a geopolitical/finance commentator.

CLAIM: {claim}
CONTEXT: {context}

Categories:
- prediction: forecasts what WILL happen (testable future outcome)
- prescription: says what SHOULD happen / needs to happen (advice, not a forecast)
- fact: statement of present/past reality
- conditional: "if X then Y" forecast

If prescription and it smuggles an implicit forecast (e.g. "needs to double in 10-15 years" implies "without doubling, shortage will worsen"), extract that forecast.

Answer STRICTLY as JSON:
{{"type": "prediction|prescription|fact|conditional", "implicit_forecast": "the implicit forecast sentence, or null", "reason": "one sentence"}}"""


def classify(claim, context='', port=11435):
    body = json.dumps({
        'model': MODEL, 'stream': False, 'think': False,
        'messages': [{'role': 'user', 'content': PROMPT.format(claim=claim[:600], context=context[:600])}],
        'options': {'num_predict': 400, 'num_ctx': 32768, 'temperature': 0.1},
    })
    r = subprocess.run(['curl', '-s', '-m', '180', f'{HOST}:{port}/api/chat', '-d', body],
                       capture_output=True, text=True, timeout=200)
    try:
        content = json.loads(r.stdout)['message']['content']
        m = re.search(r'\{.*\}', content, re.S)
        return json.loads(m.group(0))
    except Exception:
        return {'type': 'unknown', 'implicit_forecast': None, 'reason': 'classify failed'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--shard', type=int, required=True)
    ap.add_argument('--stride', type=int, default=4)
    ap.add_argument('--port', type=int, required=True)
    args = ap.parse_args()
    res_file = BASE / 'data' / f'gate_results_{args.shard}.json'
    done = set()
    if res_file.exists():
        done = {e['id'] for e in json.load(open(res_file, encoding='utf-8'))}
    d = json.load(open(BASE / 'data' / 'predictions.json', encoding='utf-8'))
    preds = [p for p in d['predictions'] if not p.get('gate_status') and not p.get('removed')]
    todo = [p for p in preds[args.shard::args.stride] if p['id'] not in done]
    print(f'shard {args.shard} port {args.port}: {len(todo)} to classify', flush=True)
    results = json.load(open(res_file, encoding='utf-8')) if res_file.exists() else []
    for i, p in enumerate(todo):
        res = classify(p['claim'], p.get('transcript_excerpt') or '', args.port)
        res['id'] = p['id']
        results.append(res)
        if (i + 1) % 10 == 0:
            res_file.write_text(json.dumps(results), encoding='utf-8')
            print(f'{i + 1}/{len(todo)}', flush=True)
    res_file.write_text(json.dumps(results), encoding='utf-8')
    from collections import Counter
    print(f'GATE_SHARD_DONE {args.shard}:', dict(Counter(r.get('type') for r in results)), flush=True)


if __name__ == '__main__':
    main()
