# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""MiroFish worker: process predictions with miro_status == 'queued'.
Runs the full MiroFish adjudication (Graphiti ingest -> panel -> verdict) via
nimo128 qwen3:32b, writes miro_result back, marks done. Silent loop (pythonw).
"""
import os
import json
import re
import subprocess
import time
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from data_lock import locked_data
import urllib.error
import urllib.request

import filelock

BASE = Path(r'C:/Users/schof/veracity2')
DATA = BASE / 'data' / 'predictions.json'
LOCK = BASE / 'data' / 'predictions.json.lock'
PANEL = Path(r'C:/Users/schof/veracity-panel/backend')
FIXTURES = PANEL / 'app' / 'fixtures'
RUNNER = PANEL / 'scripts' / 'run_claim_adjudication.py'
OUTDIR = BASE / 'data' / 'miro_verdicts'
OUTDIR.mkdir(exist_ok=True)
PY = r'C:/Users/schof/AppData/Local/hermes/tools/python-3.14.7+20260901-win32-x64/python.exe'
VPY = r'C:/Users/schof/veracity-panel/backend/.venv311/Scripts/python.exe'  # py3.11 + graphiti/oasis (rebuilt Oct 8)
ENV_BASE = {
    **{k: v for k, v in __import__('os').environ.items() if k != 'PYTHONPATH'},  # stray PYTHONPATH shadows the venv's compiled modules
    'JAVA_HOME': r'C:/Users/schof/tools/jdk-21.0.12.1+1',
    'LLM_MODEL_NAME': 'qwen3:32b',
    'LLM_BASE_URL': 'http://127.0.0.1:8899/v1',   # proxy -> nimo (embed fixups live here)
    'VERDICT_MODEL_NAME': 'qwen3:32b',
    'NEO4J_PASSWORD': 'veracitypanel',
}

LOG = BASE / 'data' / 'miro_worker.log'


def log(msg):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def ensure_services():
    """Neo4j (7474) + LLM proxy (8899) must be listening."""
    def up(port):
        try:
            urllib.request.urlopen(f'http://127.0.0.1:{port}', timeout=4)
            return True
        except urllib.error.HTTPError:
            return True  # got HTTP response = listening
        except Exception:
            return False
    if not up(7474):
        log('starting Neo4j')
        subprocess.Popen(
            ['C:/Users/schof/AppData/Local/hermes/tools/git-2.53.0+3-win32-x64/usr/bin/bash.exe', '-lc',
             'export JAVA_HOME="C:/Users/schof/tools/jdk-21.0.12.1+1"; '
             'export PATH="$JAVA_HOME/bin:$PATH"; '
             'cd /c/Users/schof/tools/neo4j-community-5.26.0 && bin/neo4j.bat console'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=0x08000000)
        # wait for bolt to actually accept
        for _ in range(20):
            time.sleep(5)
            try:
                urllib.request.urlopen('http://127.0.0.1:7474', timeout=4)
                log('neo4j http up')
                break
            except Exception:
                continue
    if not up(8899):
        log('starting LLM proxy')
        subprocess.Popen(
            [PY, r'C:/Users/schof/tools/llm_proxy.py'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=0x08000000)
        time.sleep(3)


def build_fixture(pred):
    """Prediction -> MiroFish claim fixture JSON."""
    year_m = re.search(r'\b(20[2-9]\d)\b', pred.get('claim', ''))
    fixture = {
        'claim_id': f"marty-{pred['id']}",
        'statement': pred['claim'],
        'domain': 'geopolitics_finance',
        'time_horizon': year_m.group(0) if year_m else 'next-12-months',
        'jurisdiction': 'global',
        'sources': [
            {'title': pred.get('source_url') or 'source', 'kind': 'primary_source',
             'locator': pred.get('source_url') or 'none'},
        ],
        'evidence_text': (pred.get('transcript_excerpt') or pred.get('claim') or '')[:2000],
        'notes': f"Made by {pred['individual_name']} on {pred.get('date', 'unknown date')}. Marty marked: {pred.get('marty_note') or 'ungraded'}.",
    }
    path = FIXTURES / f"marty_{pred['id']}.json"
    path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False), encoding='utf-8')
    return path


def process(pred):
    log(f"adjudicating {pred['id']}: {pred['claim'][:70]}")
    fixture = build_fixture(pred)
    out = OUTDIR / f"verdict_{pred['id']}.json"
    env = dict(ENV_BASE)
    r = subprocess.run(
        [VPY, str(RUNNER), '--claim-json', str(fixture), '--output', str(out), '--rounds', '2'],
        cwd=str(PANEL), env=env, capture_output=True, text=True, timeout=3600)
    tail = (r.stdout or '') + (r.stderr or '')
    log(f"runner exit {r.returncode}: {tail[-300:]}")
    if r.returncode == 0 and out.exists():
        v = json.loads(out.read_text(encoding='utf-8'))
        with open(DATA, encoding='utf-8') as f:
            data = json.load(f)
        target = next(x for x in data['predictions'] if x['id'] == pred['id'])
        target['miro_status'] = 'done'
        target['miro_result'] = {
            'verdict': v.get('final_verdict') or v.get('verdict') or v.get('label') or str(v)[:120],
            'confidence': v.get('confidence'),
            'summary': str(v.get('summary') or v.get('rationale') or '')[:500],
        }
        with locked_data() as fresh:
            fidx = {q['id']: i2 for i2, q in enumerate(fresh['predictions'])}
            fresh['predictions'][fidx[pred['id']]] = target
        log(f"{pred['id']} miro verdict saved")
    else:
        with open(DATA, encoding='utf-8') as f:
            data = json.load(f)
        target = next(x for x in data['predictions'] if x['id'] == pred['id'])
        with locked_data() as fresh:
            fidx = {q['id']: i2 for i2, q in enumerate(fresh['predictions'])}
            fresh['predictions'][fidx[pred['id']]] = {**target, 'miro_status': 'error'}
        log(f"{pred['id']} FAILED")


def main():
    lockf = r'C:/Users/schof/veracity2/data/miro_worker.instance.lock'
    if os.path.exists(lockf):
        try:
            old_pid = int(open(lockf).read().strip())
            ps = subprocess.run(['powershell', '-c', f'Get-Process -Id {old_pid} -ErrorAction SilentlyContinue'], capture_output=True)
            if ps.returncode == 0:
                log(f'another worker (pid {old_pid}) alive - exiting')
                return
        except Exception:
            pass
    open(lockf, 'w').write(str(os.getpid()))
    log('miro worker started (nimo via proxy; 7-GPU pool skipped)')
    while True:
        try:
            data = json.load(open(DATA, encoding='utf-8'))
            queue = [p for p in data['predictions'] if p.get('miro_status') == 'queued']
            if queue:
                ensure_services()
                process(queue[0])
            else:
                time.sleep(60)
        except BaseException as e:  # NEVER die: log full type + traceback and retry
            import traceback
            log(f"worker error: {type(e).__name__}: {e}")
            log(traceback.format_exc()[-800:])
            time.sleep(120)


if __name__ == '__main__':
    main()
