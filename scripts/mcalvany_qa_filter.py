# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""QA-filter McAlvany batch: local-Mac judge reviews every prediction; violators deleted."""
import sys, json, re
sys.path.insert(0, r'C:/Users/schof/veracity2')
from src.pipeline import call_llm

PATH = r'C:/Users/schof/veracity2/data/predictions.json'
d = json.load(open(PATH, encoding='utf-8'))
mc = [p for p in d['predictions'] if p.get('individual_name') == 'David McAlvany']

SYSTEM = (
    "You are a QA judge reviewing extracted predictions attributed to David McAlvany. "
    "Reject a prediction if it: (1) describes current/past conditions rather than a future "
    "prediction, (2) is quoted material or another person's statement, (3) is not from "
    "McAlvany's own voice, (4) is untestable opinion with no outcome. "
    "You are given numbered claims. Return JSON: {\"reject\": [numbers]} — only genuinely "
    "violating numbers. Be conservative."
)

reject_ids = set()
for i in range(0, len(mc), 8):
    batch = mc[i:i+8]
    lines = "\n".join(f"{j+1}. ({p['date']}) {p['claim'][:200]}" for j, p in enumerate(batch))
    raw = call_llm(SYSTEM, f"Claims:\n{lines}\n\nReturn the JSON now.", max_tokens=600)
    if not raw:
        continue
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        continue
    try:
        for n in json.loads(m.group(0)).get('reject', []):
            if isinstance(n, int) and 1 <= n <= len(batch):
                reject_ids.add(batch[n-1]['id'])
    except json.JSONDecodeError:
        pass

before = len(d['predictions'])
d['predictions'] = [p for p in d['predictions'] if p['id'] not in reject_ids]
json.dump(d, open(PATH, 'w', encoding='utf-8'), indent=2, ensure_ascii=False)
print(f"QA rejected {len(reject_ids)} of {len(mc)}; {before} -> {len(d['predictions'])}")
for p in mc:
    if p['id'] in reject_ids:
        print('  DEL:', p['date'], p['claim'][:80])
