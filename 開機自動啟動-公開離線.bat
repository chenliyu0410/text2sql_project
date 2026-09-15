@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
call "%~dp0公開離線啟動.bat"
exit /b %ERRORLEVEL%
