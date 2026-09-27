@echo off
setlocal
cd /d "%~dp0"
set "ANIMALESE_OPEN_BROWSER=1"
if not exist ".venv\Scripts\python.exe" (
  echo Python environment is missing. Run setup first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" app.py
