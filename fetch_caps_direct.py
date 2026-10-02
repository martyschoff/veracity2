"""Fetch captions by pulling the timedtext URL from yt-dlp metadata and downloading separately."""
import json, subprocess, time, random, re, os, sys

os.chdir(r"C:/Users/schof/veracity2")
OUT = "data/speaker_test"
VIDS = {"eWTfjnkaH0c": "moonshots_susskind", "LN92sWO2i9U": "moonshots_housel", "WsyPVdDjs2Y": "zeihan_solo"}

def clean(vtt):
    lines=[]
    for ln in vtt.splitlines():
        ln=ln.strip()
        if not ln or '-->' in ln or ln.startswith(('WEBVTT','Kind:','Language:','NOTE')) or re.match(r'^\d+$',ln):
            continue
        ln=re.sub(r'<[^>]+>','',ln)
        if lines and lines[-1]==ln: continue
        lines.append(ln)
    txt='\n>>'.join(lines)
    return txt

import httpx
for vid,name in VIDS.items():
    txtfile=f"{OUT}/{name}.txt"
    if os.path.exists(txtfile) and os.path.getsize(txtfile)>1000:
        print(name,"already"); continue
    p=subprocess.run(["python","-m","yt_dlp","-J","--skip-download",
        "--extractor-args","youtube:player_client=android_vr",
        f"https://www.youtube.com/watch?v={vid}"],capture_output=True,text=True,timeout=300)
    j=json.loads(p.stdout.strip().splitlines()[-1])
    caps=j.get("automatic_captions") or {}
    track=caps.get("en-orig") or caps.get("en") or caps.get("en-US-orig")
    if not track:
        print(name,"NO TRACK", list(caps)[:10]); continue
    url=[t for t in track if t["ext"]=="vtt"][0]["url"]
    got=None
    for attempt in range(6):
        r=httpx.get(url, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/147.0 Safari/537.36"}, timeout=60, follow_redirects=True)
        print(name, attempt, r.status_code)
        if r.status_code==200:
            got=r.text; break
        time.sleep(15+random.random()*20)
    if got:
        open(txtfile,"w",encoding="utf-8").write(clean(got))
        print(name,"WROTE",len(got))
    else:
        print(name,"FAILED")
