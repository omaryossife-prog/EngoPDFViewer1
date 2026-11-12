@echo off
setlocal
cd /d "%~dp0"
echo.
echo ENGO Secure Signing Setup
echo =========================
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\setup_engo_signing_secret.ps1"
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" (
  echo Setup did not complete. Read the message above.
) else (
  echo Signing secret setup completed.
)
pause
exit /b %EXITCODE%
