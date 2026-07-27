@echo off
cd /d "%~dp0"
echo Opening Civitai in a browser. Log in (email/Google + any 2FA), then leave it.
echo The tool auto-detects login and saves the session. Do NOT close it early.
".venv\Scripts\python.exe" civitai_upload.py login
pause
