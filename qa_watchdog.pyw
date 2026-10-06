import subprocess, time, sys, os
PY = r'C:/Users/schof/AppData/Local/hermes/tools/python-3.14.7+20260901-win32-x64/python.exe'
ENV = dict(os.environ, PYTHONPATH=r'C:/Users/schof/AppData/Local/hermes/installs/68892bcc158bcc92/environments/1f4547f85ff249b3a7b6459818be77a5/venv/Lib/site-packages')
while True:
    alive = False
    try:
        import urllib.request
        with urllib.request.urlopen('http://127.0.0.1:8765/', timeout=8) as resp:
            alive = len(resp.read()) > 10000
    except Exception:
        alive = False
    if not alive:
        subprocess.Popen([PY, '-m', 'uvicorn', 'src.app:app', '--host', '127.0.0.1', '--port', '8765'],
                         cwd=r'C:/Users/schof/veracity2', env=ENV,
                         creationflags=0x08000000)  # CREATE_NO_WINDOW
    time.sleep(60)
