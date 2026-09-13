@echo off
setlocal
echo [기후노트 빌드 스크립트]
if not exist "%~dp0.venv\Scripts\python.exe" (
    echo ERROR: Project .venv\Scripts\python.exe is missing. Set up Python 3.13 with requirements-lock.txt before building.
    exit /b 2
)
"%~dp0.venv\Scripts\python.exe" "%~dp0build_app.py"
exit /b %errorlevel%
