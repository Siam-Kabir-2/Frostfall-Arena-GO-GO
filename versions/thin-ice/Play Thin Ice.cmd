@echo off
setlocal
cd /d "%~dp0"
for %%P in (".venv\Scripts\python.exe") do (
    if exist "%%~P" (
        "%%~P" -B -c "import panda3d.core" >nul 2>&1
        if not errorlevel 1 (
            "%%~P" -B thin_ice.py %*
            goto finished
        )
    )
)
py -3 -B -c "import panda3d.core" >nul 2>&1
if not errorlevel 1 (
    py -3 -B thin_ice.py %*
    goto finished
)
python -B -c "import panda3d.core" >nul 2>&1
if not errorlevel 1 (
    python -B thin_ice.py %*
    goto finished
)
echo Thin Ice needs Python 3 and Panda3D.
echo Install it with: python -m pip install -r requirements.txt
pause
exit /b 1

:finished
if errorlevel 1 (
    echo Thin Ice closed with an error.
    pause
    exit /b 1
)
exit /b 0
