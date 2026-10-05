@echo off
REM Build (if needed) and start the AccreditDraft frontend on http://127.0.0.1:3000
cd /d "%~dp0"

if not exist "node_modules" (
  echo [setup] Installing frontend dependencies ...
  call npm install --no-audit --no-fund
)

if not exist ".next\BUILD_ID" (
  echo [setup] Building frontend ...
  call npm run build
)

python scripts\start_web.py %*
