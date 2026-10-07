# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
import json, re
d=json.load(open('data/predictions.json'))
done_urls={p['source_url'] for p in d['predictions']}
earliest={'ZeihanonGeopolitics':'2026-08-12','GZEROMedia':'2026-09-18','PeterHDiamandis':'2024-11-08'}
files={'ZeihanonGeopolitics':'videos_ZeihanonGeopolitics.txt','GZEROMedia':'videos_GZEROMedia.txt','PeterHDiamandis':'videos_PD2.txt'}
names={'ZeihanonGeopolitics':'Peter Zeihan','GZEROMedia':'Ian Bremmer','PeterHDiamandis':'Peter Diamandis'}
queue={}
for ch,f in files.items():
    vids=[]
    for line in open(f, encoding='utf-8'):
        parts=line.rstrip('\n').split('|',2)
        if len(parts)<3: continue
        vid,dt,title=parts
        if not re.match(r'^\d{8}$',dt): continue
        iso=f"{dt[:4]}-{dt[4:6]}-{dt[6:]}"
        if iso < '2024-04-30' or iso >= earliest[ch]: continue
        if ch=='GZEROMedia' and not any(k in title.lower() for k in ['quick take','ian explain','ask ian']): continue
        url=f'https://www.youtube.com/watch?v={vid}'
        if url in done_urls: continue
        vids.append({'date':iso,'id':vid,'title':title})
    vids.sort(key=lambda v:v['date'])
    queue[ch]=vids
    print(ch, names[ch], len(vids), 'oldest:', vids[0]['date'] if vids else None, 'newest:', vids[-1]['date'] if vids else None)
json.dump(queue, open('work_queue.json','w'), indent=1)
