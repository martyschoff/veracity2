import json, subprocess, sys

def listing(ch_file):
    vids=[]
    for line in open(ch_file, encoding='utf-8'):
        parts=line.rstrip('\n').split('|',2)
        if len(parts)<3: continue
        vid,dt,title=parts
        if not vid or len(vid)!=11: continue
        vids.append({'id':vid,'approx':dt,'title':title})
    return vids  # index 0 = newest

def real_date(vid):
    r=subprocess.run(['python','-m','yt_dlp','--skip-download','--no-warnings',
        '--print','%(upload_date)s', f'https://www.youtube.com/watch?v={vid}'],
        capture_output=True,text=True,timeout=120)
    for tok in r.stdout.split():
        if len(tok)==8 and tok.isdigit(): return tok
    return None

def iso(d): return f'{d[:4]}-{d[4:6]}-{d[6:]}' if d else None

ch_file=sys.argv[1]
vids=listing(ch_file)
lo,hi=0,len(vids)-1
# find smallest index with real_date < '20240430' (listing is newest-first)
boundary=len(vids)
lo,hi=0,len(vids)-1
while lo<=hi:
    mid=(lo+hi)//2
    d=real_date(vids[mid]['id'])
    print(vids[mid]['id'],d, flush=True)
    if d is None: mid+=1; continue
    if d < '20240430':
        boundary=mid; hi=mid-1
    else:
        lo=mid+1
print('BOUNDARY_INDEX',boundary, 'of', len(vids))
print('sample around boundary:')
for i in range(max(0,boundary-2), min(len(vids),boundary+3)):
    print(i, vids[i]['id'], vids[i]['approx'], real_date(vids[i]['id']), vids[i]['title'][:60])
json.dump({'boundary':boundary}, open(f'boundary_{ch_file}','w'))
