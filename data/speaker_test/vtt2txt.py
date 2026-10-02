import glob, re
def vtt2txt(p):
    lines=[]
    for ln in open(p, encoding='utf-8'):
        ln=ln.strip()
        if not ln or '-->' in ln or ln.startswith(('WEBVTT','Kind:','Language:')) or re.match(r'^\d+$',ln) or ln.startswith('NOTE'):
            continue
        ln=re.sub(r'<[^>]+>','',ln)
        if lines and lines[-1]==ln: continue
        lines.append(ln)
    txt=' '.join(lines)
    txt=re.sub(r'>>','\n>>',txt)
    open(p.rsplit('.',1)[0]+'.txt','w',encoding='utf-8').write(txt)
    return len(txt)
for p in glob.glob('*.vtt')+glob.glob('*.srt'):
    print(p, vtt2txt(p))
