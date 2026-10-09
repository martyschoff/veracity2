import subprocess, time, os, datetime
DAEMONS = [
    ('miro', r'C:/Users/schof/veracity2/scripts/miro_worker.py', r'C:/Users/schof/veracity2/data/miro_worker.instance.lock'),
    ('swarm', r'C:/Users/schof/veracity2/scripts/swarm_worker.py', r'C:/Users/schof/veracity2/data/swarm_worker.lock'),
    ('delphicursor', r'C:/Users/schof/veracity2/scripts/delphicursor_worker.py', r'C:/Users/schof/veracity2/data/delphicursor.lock'),
    ('harvest', r'C:/Users/schof/veracity2/scripts/harvest_daemon.py', r'C:/Users/schof/veracity2/data/harvest.lock'),
    ('watchdog', r'C:/Users/schof/veracity2/scripts/watchdog_loop.py', None),
]
LOG = r'C:/Users/schof/veracity2/data/fleetkeeper.log'
PYW = r'C:/Users/schof/AppData/Local/hermes/tools/python-3.14.7+20260901-win32-x64/pythonw.exe'
def log(m):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {m}"
    print(line, flush=True)
    open(LOG, 'a', encoding='utf-8').write(line + '\n')
def alive(name):
    r = subprocess.run(['powershell','-c',f"Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | ForEach {{ $cl=(Get-CimInstance Win32_Process -Filter \"ProcessId=$($_.ProcessId)\").CommandLine; if ($cl -like '*{name}*') {{ exit 0 }} }}; exit 1"], capture_output=True)
    return r.returncode == 0
log('fleetkeeper started (10-min patrol)')
while True:
    for name, script, lockf in DAEMONS:
        if not alive(name):
            log(f'{name} DEAD - relaunching')
            if lockf and os.path.exists(lockf):
                try: os.remove(lockf)
                except OSError: pass
            subprocess.Popen([PYW, script], creationflags=0x08000000)
    time.sleep(600)
