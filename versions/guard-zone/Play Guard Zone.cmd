@echo off
setlocal
cd /d "%~dp0"
for %%P in (".venv\Scripts\python.exe") do (
    if exist "%%~P" (
        "%%~P" -B -c "import panda3d.core" >nul 2>&1
        if not errorlevel 1 (
            "%%~P" -B guard_zone.py %*
            goto finished
        )
    )
)
py -3 -B -c "import panda3d.core" >nul 2>&1
if not errorlevel 1 (
    py -3 -B guard_zone.py %*
    goto finished
)
python -B -c "import panda3d.core" >nul 2>&1
if not errorlevel 1 (
    python -B guard_zone.py %*
    goto finished
)
echo Guard Zone needs Python 3 and Panda3D.
echo Install it with: python -m pip install -r requirements-3d.txt
pause
exit /b 1

:finished
if errorlevel 1 (
    echo Guard Zone closed with an error.
    pause
    exit /b 1
)
exit /b 0
