@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -B -c "import panda3d.core" >nul 2>&1
    if not errorlevel 1 (
        ".venv\Scripts\python.exe" -B gogo3d.py %*
        goto finished
    )
)
py -3 -B -c "import panda3d.core" >nul 2>&1
if not errorlevel 1 (
    py -3 -B gogo3d.py %*
    goto finished
)
python -B -c "import panda3d.core" >nul 2>&1
if not errorlevel 1 (
    python -B gogo3d.py %*
    goto finished
)
echo Frostfall Arena Go Go 3D needs Python and Panda3D.
echo Set up a local environment with:
echo   python -m venv .venv
echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
pause
exit /b 1

:finished
if errorlevel 1 (
    echo Frostfall Arena Go Go 3D closed with an error.
    pause
    exit /b 1
)
exit /b 0
