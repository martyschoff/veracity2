# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.

import subprocess, time, json, sys, datetime
LOG = r'C:/Users/schof/veracity2/data/swarm_worker.log'
def log(m):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {m}"
    print(line, flush=True)
    open(LOG, 'a', encoding='utf-8').write(line + '\n')
import os
LOCKF = r'C:/Users/schof/veracity2/data/swarm_worker.lock'
if os.path.exists(LOCKF):
    try:
        opid = int(open(LOCKF).read().strip())
        if subprocess.run(['powershell','-c',f'Get-Process -Id {opid} -ErrorAction SilentlyContinue'], capture_output=True).returncode == 0:
            log(f'another swarm worker (pid {opid}) alive - exit')
            sys.exit(0)
    except Exception: pass
open(LOCKF,'w').write(str(os.getpid()))
log('swarm worker started (poll 60s)')
while True:
    try:
        p = json.load(open(r'C:/Users/schof/veracity2/data/predictions.json', encoding='utf-8'))
        q = sum(1 for x in p['predictions'] if x.get('mc_status') == 'queued')
        if q:
            log(f'{q} queued - running monte_carlo pass')
            r = subprocess.run(['python', r'C:/Users/schof/veracity2/scripts/monte_carlo.py'], capture_output=True, text=True, timeout=7200)
            log(f'pass exit {r.returncode}: {(r.stdout or r.stderr)[-300:]}')
        time.sleep(60)
    except BaseException as e:
        log(f'error {type(e).__name__}: {e}')
        time.sleep(120)
