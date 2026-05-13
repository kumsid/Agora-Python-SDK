@echo off
setlocal
cd /d "%~dp0"
python scripts\setup_native_sdk.py %*
exit /b %ERRORLEVEL%
