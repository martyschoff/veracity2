# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Extract David McAlvany's own-voice future predictions from McAlvany Weekly Commentary posts."""
import json, re, html, time, urllib.request, sys

LLM_URL = 'http://127.0.0.1:18434/v1/chat/completions'
LLM_KEY = 'OyISwmqwQMak4mEOtO3zajuzSY8clG73'
MODEL = 'Qwen3.8-27B-UD-Q4_K_M'
DATA = r'C:/Users/schof/veracity2/data/predictions.json'

PROMPT = """You are extracting PREDICTIONS made by David McAlvany from a transcript of the McAlvany Weekly Commentary podcast.

STRICT RULES:
- Only extract claims in DAVID McALVANY's own voice (lines labeled "David:"). NEVER extract from Kevin's lines, quoted material, attributed quotes, guest statements, or anything inside quotation marks attributed to someone else — even if David endorses it.
- Only FUTURE predictions relative to the article date ({date}). If a claim references a year or event already in the past relative to {date}, exclude it. Statements of current fact or history are NOT predictions.
- Prioritize MEASURABLE predictions: specific dates, dollar amounts, prices, percentages, rate levels.
- Maximum 2 predictions. If nothing qualifies, return an empty array.

Return ONLY a JSON array (no markdown), each element:
{{"claim": "...", "measurement_type": "quantitative" or "subjective", "excerpt": "short verbatim quote from David's lines supporting it"}}

Transcript (article date {date}):
---
{text}
---"""


def clean(html_content):
    t = re.sub(r'<script.*?</script>', ' ', html_content, flags=re.S)
    t = re.sub(r'<style.*?</style>', ' ', t, flags=re.S)
    t = re.sub(r'<[^>]+>', ' ', t)
    t = html.unescape(t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


MAC = 'http://upthread64.tail5b3b50.ts.net:11434/v1/chat/completions'


def _post(url, prompt, model, key=None, timeout=300):
    body = json.dumps({'model': model, 'messages': [{'role': 'user', 'content': prompt}],
                       'max_tokens': 2500, 'temperature': 0.2}).encode()
    hdrs = {'Content-Type': 'application/json'}
    if key:
        hdrs['Authorization'] = 'Bearer ' + key
    req = urllib.request.Request(url, data=body, headers=hdrs)
    r = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
    m = r['choices'][0]['message']
    return m.get('content') or m.get('reasoning_content') or ''


def call_llm(prompt, timeout=300):
    for url, model, key in ((LLM_URL, MODEL, LLM_KEY), (MAC, 'qwen3-coder:30b-32k', None)):
        try:
            return _post(url, prompt, model, key, timeout)
        except Exception as e:
            print('  endpoint fail', url.split('//')[1][:30], e)
    raise RuntimeError('all LLM endpoints failed')


def parse_items(text):
    m = re.search(r'\[.*\]', text, re.S)
    if not m:
        return []
    try:
        items = json.loads(m.group(0))
    except Exception:
        return []
    return [i for i in items if isinstance(i, dict) and i.get('claim')]


def year_filter(claim, src_date):
    yr = int(src_date[:4])
    for m in re.finditer(r'\b(20\d\d)\b', claim):
        if int(m.group(1)) < yr:
            return False
    return True


def main():
    content = json.load(open(r'C:/Users/schof/veracity2/data/mcalvany_wc_content.json'))
    # already processed?
    d = json.load(open(DATA, encoding='utf-8'))
    done_urls = {p['source_url'] for p in d['predictions'] if p['individual_name'] == 'David McAlvany'}
    ids = sorted(content.keys(), key=lambda k: content[k]['date'], reverse=True)
    results = []
    for pid in ids:
        p = content[pid]
        if p['link'] in done_urls:
            print('SKIP(done)', p['link']); continue
        text = clean(p['content']['rendered'])
        i = text.find('Welcome to the McAlvany Weekly Commentary')
        if i > 0:
            text = text[i:]
        if len(text) > 14000:
            text = text[:14000]
        prompt = PROMPT.format(date=p['date'][:10], text=text)
        ok = False
        for attempt in range(3):
            try:
                raw = call_llm(prompt)
                items = parse_items(raw)[:2]
                items = [i for i in items if year_filter(i['claim'], p['date'])]
                results.append({'post_id': pid, 'date': p['date'][:10], 'url': p['link'],
                                'title': p['title']['rendered'], 'predictions': items})
                ok = True
                break
            except Exception as e:
                print('ERR', pid, attempt, e); time.sleep(5)
        print(('OK ' if ok else 'FAIL '), p['date'][:10], len(items if ok else []), p['link'])
        json.dump(results, open(r'C:/Users/schof/veracity2/data/mcalvany_wc_extractions.json', 'w'), indent=1)


if __name__ == '__main__':
    main()
