@echo off
REM Usage: upload.bat "path\to\model.civitai.json"
REM Drag a config file onto this .bat, or pass it as an argument.
cd /d "%~dp0"
if "%~1"=="" (
    echo Usage: upload.bat "path\to\model.civitai.json"
    echo   or drag a .civitai.json file onto this file.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" civitai_upload.py upload "%~1" --keep-open
pause
