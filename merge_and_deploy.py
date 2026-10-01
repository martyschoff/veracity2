import json, os, time, hashlib, subprocess, sys
os.chdir('C:/Users/schof/veracity2')

# merge staged -> predictions.json (dedup by source_url+claim)
data=json.load(open('data/predictions.json'))
existing={(p['source_url'],p['claim']) for p in data['predictions']}
staged=[]
if os.path.exists('staged_predictions.jsonl'):
    for l in open('staged_predictions.jsonl',encoding='utf-8'):
        try:
            r=json.loads(l)
            if (r['source_url'],r['claim']) not in existing:
                existing.add((r['source_url'],r['claim']))
                staged.append(r)
        except Exception: pass
if staged:
    data['predictions'].extend(staged)
    json.dump(data,open('data/predictions.json','w'),ensure_ascii=False,indent=2)
print('merged',len(staged))

# per-person earliest
from collections import Counter
c=Counter(p['individual_name'] for p in data['predictions'])
for n in ['Peter Zeihan','Ian Bremmer','Peter Diamandis','Doomberg']:
    ds=sorted(p['date'] for p in data['predictions'] if p['individual_name']==n)
    print(n,c[n],ds[0] if ds else None)

r=subprocess.run(['C:/Users/schof/AppData/Local/hermes/tools/python-3.14.7+20260901-win32-x64/python.exe','render.py'],
                 capture_output=True,text=True,timeout=200)
print('render rc',r.returncode,(r.stdout or r.stderr)[-300:])
r=subprocess.run(['surge','surge_dist/','veracity2.surge.sh'],capture_output=True,text=True,timeout=200,
                 env={**os.environ,'SURGE_TOKEN':'ea807c6f912951573c26c7fed2788f3f'})
print('surge rc',r.returncode,(r.stdout or r.stderr)[-200:])
