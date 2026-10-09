@echo off
REM Quick worker health check script
cd /d "%~dp0"
python scripts\watchdog.py --notify
pause