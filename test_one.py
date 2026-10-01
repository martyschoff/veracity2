import json, sys, re, time
from hermes_tools import web_extract

queue=json.load(open('work_queue.json'))
ch=sys.argv[1]; idx=int(sys.argv[2])
v=queue[ch][idx]
print('TEST', v)
res=web_extract(urls=[f"https://www.youtube.com/watch?v={v['id']}"], char_limit=20000)
c=res['results'][0].get('content','')
print('LEN', len(c))
print(c[:1500])
m=re.search(r'## Transcript', c)
print('HAS_TRANSCRIPT', bool(m))
i=c.find('## Transcript')
print(c[i:i+800] if i>=0 else 'NO TRANSCRIPT SECTION')
