@echo off
powershell -c "if (-not (Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\").CommandLine | Select-String -Quiet 'miro_worker') { Start-Process 'C:/Users/schof/AppData/Local/hermes/tools/python-3.14.7+20260901-win32-x64/pythonw.exe' -ArgumentList 'C:/Users/schof/veracity2/scripts/miro_worker.py' -WindowStyle Hidden }"
