
import subprocess, time, datetime, json
log = r'C:/Users/schof/veracity2/data/delphicursor_worker.log'
status = r'C:/Users/schof/veracity2/data/delphicursor_watch_status.txt'
done_before = 0
try: done_before = sum(1 for x in json.load(open(r'C:/Users/schof/veracity2/data/predictions.json', encoding='utf-8'))['predictions'] if x.get('delphicursor_result'))
except Exception: pass
while True:
    now = datetime.datetime.now().strftime('%H:%M:%S')
    alive = subprocess.run(['powershell','-c',"Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | ForEach { $cl=(Get-CimInstance Win32_Process -Filter \"ProcessId=$($_.ProcessId)\").CommandLine; if ($cl -like '*delphicursor_worker*') { exit 0 } }; exit 1"], capture_output=True).returncode == 0
    try:
        done_now = sum(1 for x in json.load(open(r'C:/Users/schof/veracity2/data/predictions.json', encoding='utf-8'))['predictions'] if x.get('delphicursor_result'))
    except Exception:
        done_now = 0
    tail = open(log, encoding='utf-8', errors='replace').read().splitlines()[-3:]
    txt = f"check {now} | worker alive: {alive} | cursor verdicts: {done_now} (was {done_before})\n" + "\n".join(tail)
    open(status, 'w').write(txt)
    if done_now > done_before or 'ALL_QUEUE_DONE' in '\n'.join(tail):
        txt += '\n=== DELPHICURSOR CASES COMPLETE ==='
        open(status, 'w').write(txt)
        break
    if not alive:
        subprocess.Popen([r'C:/Users/schof/AppData/Local/hermes/tools/python-3.14.7+20260901-win32-x64/pythonw.exe', r'C:/Users/schof/veracity2/scripts/delphicursor_worker.py'], creationflags=0x08000000)
    time.sleep(240)
