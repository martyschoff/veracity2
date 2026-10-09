# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.

import subprocess, time, json, sys, datetime, os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
LOG = BASE / 'data' / 'swarm_worker.log'
HEARTBEAT_FILE = BASE / 'data' / 'swarm_heartbeat.txt'
LOCKF = BASE / 'data' / 'swarm_worker.lock'
PREDICTIONS_FILE = BASE / 'data' / 'predictions.json'
MONTE_CARLO_SCRIPT = BASE / 'scripts' / 'monte_carlo.py'

def log(m):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {m}"
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def write_heartbeat():
    try:
        with open(HEARTBEAT_FILE, 'w', encoding='utf-8') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S'))
    except Exception:
        pass
if LOCKF.exists():
    try:
        opid = int(LOCKF.read_text().strip())
        if subprocess.run(['powershell','-c',f'Get-Process -Id {opid} -ErrorAction SilentlyContinue'], capture_output=True).returncode == 0:
            log(f'another swarm worker (pid {opid}) alive - exit')
            sys.exit(0)
    except Exception: pass
LOCKF.write_text(str(os.getpid()))
log('swarm worker started (poll 60s)')
while True:
    try:
        # Write heartbeat
        write_heartbeat()
        
        with open(PREDICTIONS_FILE, encoding='utf-8') as f:
            p = json.load(f)
        q = sum(1 for x in p['predictions'] if x.get('mc_status') == 'queued')
        if q:
            log(f'{q} queued - running monte_carlo pass')
            r = subprocess.run(['python', str(MONTE_CARLO_SCRIPT)], capture_output=True, text=True, timeout=7200, cwd=str(BASE))
            log(f'pass exit {r.returncode}: {(r.stdout or r.stderr)[-300:]}')
        time.sleep(60)
    except BaseException as e:
        log(f'error {type(e).__name__}: {e}')
        time.sleep(120)
