# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Full speaker-attribution resweep of existing predictions.
Batched LLM judge over data/qa_queue.json; results checkpoint to data/qa_results.json.
"""
import json, urllib.request, time, os, sys

REPO = 'C:/Users/schof/veracity2'
QUEUE = f'{REPO}/data/qa_queue.json'
OUT = f'{REPO}/data/qa_results.json'

SYS = """You are a speaker-attribution auditor. Each item is a prediction currently filed under a TRACKED individual, with the video title, channel, the claim, and a transcript excerpt from the source.
Decide for each: was the claim made by the tracked individual in their OWN voice, or by a guest / interviewer / quoted third party?
Rules (STRICT OWNERSHIP): a prediction belongs only to whoever ARTICULATED the substantive claim.
- Remove (misattributed) if the excerpt shows the claim was spoken by a guest, interviewer, or quoted third party (excerpt names another speaker, "my guest", a quotation attributed to someone else, or a third-person reference like "Peter says...").
- Remove if the excerpt shows the tracked individual only BARELY ASSENTED to a claim actually articulated by someone else ("yes", "100%", "absolutely", "I agree") — assent does NOT transfer ownership.
- Empty excerpt -> keep unless the title clearly shows an interview whose main speaker is a named guest rather than the tracked individual.
- Uncertain -> keep.
Reply ONLY JSON: {"results":[{"i":<idx>,"verdict":"keep"|"remove","confidence":0-1,"reason":"<short>","speaker":"<name or empty>"}]} with exactly one entry per item, in order."""

ENDPOINTS = [
    ('http://100.120.21.39:11500/v1/chat/completions', 'qwen3-coder:30b-32k', None),
    ('http://127.0.0.1:18434/v1/chat/completions', 'Qwen3.8-27B-UD-Q4_K_M', 'OyISwmqwQMak4mEOtO3zajuzSY8clG73'),
    ('http://100.68.43.17:11500/v1/chat/completions', 'llama3.3:70b', None),
]

def llm(messages, timeout=420):
    last = None
    for url, model, key in ENDPOINTS:
        body = {'model': model, 'messages': messages, 'max_tokens': 3000, 'temperature': 0}
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json',
                                              **({'Authorization': 'Bearer ' + key} if key else {})})
        try:
            o = json.load(urllib.request.urlopen(req, timeout=timeout))
            m = o['choices'][0]['message']
            c = m.get('content') or m.get('reasoning_content') or ''
            if c.strip():
                return c
        except Exception as e:
            last = e
            print(f'  endpoint fail {model}: {str(e)[:80]}', flush=True)
    raise RuntimeError(f'all endpoints failed: {last}')

def parse(out, idxs):
    s = out.find('{')
    e = out.rfind('}')
    data = json.loads(out[s:e+1])
    res = {}
    for r in data['results']:
        i = int(r['i'])
        if i in idxs:
            res[i] = r
    return res

def main():
    q = json.load(open(QUEUE))
    results = {}
    if os.path.exists(OUT):
        results = json.load(open(OUT))
    todo = [b for b in q if str(b['i']) not in results]
    print(f'total {len(q)}, done {len(q)-len(todo)}, todo {len(todo)}', flush=True)
    t0 = time.time()
    for s in range(0, len(todo), 8):
        batch = todo[s:s+8]
        idxs = {b['i'] for b in batch}
        items = '\n'.join(
            f"[{b['i']}] person={b['person']} channel={b['ch']} title={b['title']}\n"
            f"claim: {b['claim']}\nexcerpt: {b['ex'][:500] or '(none)'}" for b in batch)
        got = {}
        for attempt in range(3):
            try:
                out = llm([{'role': 'system', 'content': SYS}, {'role': 'user', 'content': items}])
                got = parse(out, idxs)
                if len(got) == len(idxs):
                    break
                print(f'  batch {s//8}: got {len(got)}/{len(idxs)}, retry', flush=True)
            except Exception as ex:
                print(f'  batch {s//8} attempt {attempt}: {str(ex)[:100]}', flush=True)
                time.sleep(5)
        for b in batch:
            r = got.get(b['i'], {'verdict': 'keep', 'confidence': 0, 'reason': 'unparsed/failed', 'speaker': ''})
            results[str(b['i'])] = {'id': b['id'], 'person': b['person'], 'url': b['url'],
                                    'ch': b['ch'], 'title': b['title'], 'claim': b['claim'],
                                    'verdict': r.get('verdict'), 'confidence': r.get('confidence'),
                                    'reason': r.get('reason'), 'speaker': r.get('speaker', '')}
        if (s // 8) % 5 == 4 or s + 8 >= len(todo):
            json.dump(results, open(OUT, 'w'))
            el = time.time() - t0
            done = s // 8 + 1
            print(f'batch {done}: saved {len(results)} entries; {el:.0f}s elapsed, ~{el/max(done,1):.0f}s/batch', flush=True)
    json.dump(results, open(OUT, 'w'))
    rm = [v for v in results.values() if v['verdict'] == 'remove']
    print(f'DONE. removed-flagged: {len(rm)}', flush=True)
    for v in rm:
        print(f"  REMOVE [{v['person']}] {v['claim'][:90]} | {v['reason']} | speaker={v['speaker']}", flush=True)

if __name__ == '__main__':
    main()
