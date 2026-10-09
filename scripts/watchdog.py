# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Worker health watchdog: check heartbeats and alert on stale workers.

Usage: python scripts/watchdog.py [--notify]
       --notify: show desktop notification for stale workers
"""
import argparse
import datetime
import os
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
HEARTBEAT_FILES = {
    'delphicursor': BASE / 'data' / 'delphicursor_heartbeat.txt',
    'miro': BASE / 'data' / 'miro_heartbeat.txt', 
    'swarm': BASE / 'data' / 'swarm_heartbeat.txt'
}
STALE_THRESHOLD = 300  # 5 minutes

def check_worker_health(worker_name: str, heartbeat_file: Path) -> tuple[bool, str]:
    """Check if worker is healthy. Returns (is_healthy, status_msg)."""
    if not heartbeat_file.exists():
        return False, f"{worker_name}: no heartbeat file"
    
    try:
        heartbeat_text = heartbeat_file.read_text(encoding='utf-8').strip()
        heartbeat_time = datetime.datetime.strptime(heartbeat_text, '%Y-%m-%d %H:%M:%S')
        now = datetime.datetime.now()
        age_seconds = (now - heartbeat_time).total_seconds()
        
        if age_seconds > STALE_THRESHOLD:
            return False, f"{worker_name}: stale heartbeat ({age_seconds:.0f}s old)"
        else:
            return True, f"{worker_name}: healthy ({age_seconds:.0f}s ago)"
            
    except Exception as e:
        return False, f"{worker_name}: corrupted heartbeat ({e})"

def show_notification(title: str, message: str):
    """Show Windows desktop notification."""
    try:
        if sys.platform == 'win32':
            # Use PowerShell to show notification
            cmd = [
                'powershell', '-Command',
                f'Add-Type -AssemblyName System.Windows.Forms; '
                f'[System.Windows.Forms.MessageBox]::Show("{message}", "{title}", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning)'
            ]
            subprocess.run(cmd, check=False, capture_output=True)
    except Exception:
        pass  # Notification failed, but don't crash

RESTART_MAP = {
    'delphicursor': ('delphicursor.lock', r'C:/Users/schof/veracity2/scripts/delphicursor_worker.py'),
    'miro': ('miro_worker.instance.lock', r'C:/Users/schof/veracity2/scripts/miro_worker.py'),
    'swarm': ('swarm_worker.lock', r'C:/Users/schof/veracity2/scripts/swarm_worker.py'),
}
PYW = r'C:/Users/schof/AppData/Local/hermes/tools/python-3.14.7+20260901-win32-x64/pythonw.exe'

def restart_worker(name):
    """Restart a dead worker: clear its lock and relaunch via pythonw."""
    import os
    lockf, script = RESTART_MAP[name]
    lp = BASE / 'data' / lockf
    if lp.exists():
        try: lp.unlink()
        except OSError: pass
    subprocess.Popen([PYW, script], creationflags=0x00000008)

def main():
    parser = argparse.ArgumentParser(description='Check worker health')
    parser.add_argument('--notify', action='store_true', help='Show desktop notification for stale workers')
    args = parser.parse_args()
    
    print(f"Checking worker health (stale threshold: {STALE_THRESHOLD}s)")
    
    all_healthy = True
    stale_workers = []
    
    for worker_name, heartbeat_file in HEARTBEAT_FILES.items():
        is_healthy, status_msg = check_worker_health(worker_name, heartbeat_file)
        print(f"  {status_msg}")
        
        if not is_healthy:
            all_healthy = False
            stale_workers.append(worker_name)
    
    for name in stale_workers:
        with open(BASE / 'data' / 'heartbeat_alerts.jsonl', 'a', encoding='utf-8') as fh:
            import json as _json
            fh.write(_json.dumps({'ts': datetime.datetime.now().isoformat(), 'worker': name, 'action': 'restart'}) + chr(10))
        restart_worker(name)

    if not all_healthy and args.notify:
        stale_list = ", ".join(stale_workers)
        show_notification("Veracity Workers Alert", f"Stale workers detected: {stale_list}")
    
    if all_healthy:
        print("All workers healthy")
        sys.exit(0)
    else:
        print(f"WARNING: {len(stale_workers)} stale worker(s)")
        sys.exit(1)

if __name__ == '__main__':
    main()