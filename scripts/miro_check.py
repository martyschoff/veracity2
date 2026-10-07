# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.

import subprocess, time, datetime
log = r'C:/Users/schof/veracity2/data/miro_worker.log'
status = r'C:/Users/schof/veracity2/data/miro_watch_status.txt'
while True:
    now = datetime.datetime.now().strftime('%H:%M:%S')
    alive = subprocess.run(['powershell','-c',"Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | ForEach { $cl=(Get-CimInstance Win32_Process -Filter \"ProcessId=$($_.ProcessId)\").CommandLine; if ($cl -like '*miro_worker*') { exit 0 } }; exit 1"], capture_output=True).returncode == 0
    tail = open(log, encoding='utf-8').read().splitlines()[-2:]
    txt = f"check {now} | worker alive: {alive}\n" + "\n".join(tail)
    if 'miro verdict saved' in open(log, encoding='utf-8').read():
        txt += '\n=== DELPHI RUN COMPLETE ==='
        open(status, 'w').write(txt)
        break
    open(status, 'w').write(txt)
    if not alive:
        subprocess.Popen([r'C:/Users/schof/AppData/Local/hermes/tools/python-3.14.7+20260901-win32-x64/pythonw.exe', r'C:/Users/schof/veracity2/scripts/miro_worker.py'], creationflags=0x08000000)
    time.sleep(120)
