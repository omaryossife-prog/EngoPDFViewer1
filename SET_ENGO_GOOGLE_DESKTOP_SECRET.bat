@echo off
setlocal
cd /d "%~dp0"
title Engo - Configure Google Desktop OAuth
py -3.13 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,13) else 1)" >nul 2>&1
if not errorlevel 1 goto run_py
pymanager exec 3.13 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,13) else 1)" >nul 2>&1
if not errorlevel 1 goto run_pymanager
echo Python 3.13 was not found. Run run.bat once to install/configure Python.
pause
exit /b 1
:run_py
py -3.13 tools\set_google_desktop_secret.py %*
goto result
:run_pymanager
pymanager exec 3.13 tools\set_google_desktop_secret.py %*
:result
if errorlevel 1 (
  echo.
  echo Secret setup did not complete.
) else (
  echo.
  echo Desktop OAuth secret saved locally.
)
pause
endlocal
