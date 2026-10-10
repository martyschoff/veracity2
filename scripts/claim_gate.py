# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Claim-type gate: classify a candidate claim as prediction / prescription /
fact / conditional using the local model. Used by the pipeline at extraction
and by the gate sweep over existing predictions.
"""
import json
import re
import subprocess

OLLAMA = 'http://100.84.167.88:11500/api/chat'
MODEL = 'qwen3:32b'

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


def classify(claim: str, context: str = '') -> dict:
    body = json.dumps({
        'model': MODEL, 'stream': False, 'think': False,
        'messages': [{'role': 'user', 'content': PROMPT.format(claim=claim[:600], context=context[:600])}],
        'options': {'num_predict': 250, 'temperature': 0.1},
    })
    r = subprocess.run(['curl', '-s', '-m', '300', OLLAMA, '-d', body],
                       capture_output=True, text=True, timeout=320)
    try:
        content = json.loads(r.stdout)['message']['content']
        m = re.search(r'\{.*\}', content, re.S)
        return json.loads(m.group(0))
    except Exception:
        return {'type': 'unknown', 'implicit_forecast': None, 'reason': 'classify failed'}
