@echo off
powershell -c "if (-not (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)) { Start-Process 'C:/Users/schof/AppData/Local/hermes/tools/python-3.14.7+20260901-win32-x64/python.exe' -ArgumentList '-m','uvicorn','src.app:app','--host','127.0.0.1','--port','8765' -WorkingDirectory 'C:/Users/schof/veracity2' -WindowStyle Hidden }"
