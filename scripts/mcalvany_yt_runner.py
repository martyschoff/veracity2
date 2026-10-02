import sys, os, json, re, time, threading
sys.path.insert(0, r"C:/Users/schof/veracity2/scripts")
import mcalvany_extract as m

sample = json.load(open(r"C:/Users/schof/veracity2/data/mcalvany_yt_sample.json"))
picks = ['Dollar Strength Pressures Metals','Best Risk Hedge: Gold Or Crypto?','Our Annual Q&A Part 1',
 'Silver\u2019s Explosive Rally','Why Gold\u2019s Correction Is a Gift, Not a Crisis','Gold Hits $3,400 as Fed Signals Rate Cuts',
 'Markets Shift Toward Metals','CPI Down, Dollar Up','FED Sparks Market Volatility','Metals Eye Breakout']
chosen = [o for o in sample if o.get('info','') >= '20240430' and any(o['title'].startswith(p[:20]) for p in picks)]
OUT = r"C:/Users/schof/veracity2/data/mcalvany_yt_extractions.json"
d = json.load(open(m.DATA, encoding='utf-8'))
done_urls = {p['source_url'] for p in d['predictions'] if p['individual_name'] == 'David McAlvany'}
results = json.load(open(OUT)) if os.path.exists(OUT) else []

YT_PROMPT = """You are extracting PREDICTIONS from an auto-generated YouTube caption transcript of the McAlvany Financial channel. The show is hosted by David McAlvany.

STRICT RULES:
- Only extract claims from David McAlvany, the HOST and lead voice of the show. The captions have no speaker labels. If a claim is clearly from a guest, co-host, quoted person, or you cannot tell who said it, SKIP it. When uncertain, skip.
- Only FUTURE predictions relative to the video date ({date}). Discard anything about past events/years.
- Prioritize MEASURABLE predictions: dates, dollar amounts, prices, percentages.
- Maximum 2 predictions. If nothing qualifies, return [].

Return ONLY a JSON array, each element:
{{"claim": "...", "measurement_type": "quantitative" or "subjective", "excerpt": "short caption quote"}}

Video date {date}. Title: {title}
Captions:
---
{text}
---"""

def vtt_text(path):
    t = open(path, encoding='utf-8', errors='ignore').read()
    lines = []
    for ln in t.splitlines():
        if '-->' in ln or ln.startswith(('WEBVTT','Kind:','Language:','NOTE')) or not ln.strip():
            continue
        ln = re.sub(r'<[^>]+>', '', ln).strip()
        if ln and (not lines or lines[-1] != ln):
            lines.append(ln)
    return ' '.join(lines)[:14000]

for o in chosen:
    url = 'https://www.youtube.com/watch?v=' + o['id']
    if url in done_urls or any(r.get('url') == url for r in results):
        print('SKIP', url); continue
    path = rf"C:/Users/schof/veracity2/data/yt_{o['id']}.en.vtt"
    if not os.path.exists(path):
        print('NO VTT', o['title']); continue
    text = vtt_text(path)
    date = f"{o['info'][:4]}-{o['info'][4:6]}-{o['info'][6:]}"
    items = []
    for _ in range(3):
        try:
            raw = m.call_llm(YT_PROMPT.format(date=date, title=o['title'], text=text))
            items = [x for x in m.parse_items(raw)[:2] if m.year_filter(x['claim'], date)]
            break
        except Exception as e:
            print('ERR', o['id'], e, flush=True); time.sleep(10)
    results.append({'date': date, 'url': url, 'title': o['title'], 'predictions': items})
    json.dump(results, open(OUT, 'w'), indent=1)
    print('DONE', date, len(items), o['title'][:50], flush=True)
print('ALL DONE', flush=True)
