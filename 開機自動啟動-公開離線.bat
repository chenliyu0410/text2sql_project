@echo off
setlocal EnableExtensions DisableDelayedExpansion
pushd "%~dp0" >nul 2>&1
powershell.exe -NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0scripts\public_offline_service.ps1" -Mode start
set "RESULT=%ERRORLEVEL%"
popd
exit /b %RESULT%
