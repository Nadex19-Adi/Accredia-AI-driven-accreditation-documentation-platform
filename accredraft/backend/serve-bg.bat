@echo off
REM Start the AccreditDraft API in the background and wait until it is healthy.
REM Logs to server.log. Safe to run twice - it will not start a second server.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [setup] Creating virtual environment with Python 3.10 ...
  py -3.10 -m venv .venv || python -m venv .venv
  .venv\Scripts\python.exe -m pip install --upgrade pip
  .venv\Scripts\python.exe -m pip install -r requirements.txt
)

.venv\Scripts\python.exe scripts\start_server.py %*
