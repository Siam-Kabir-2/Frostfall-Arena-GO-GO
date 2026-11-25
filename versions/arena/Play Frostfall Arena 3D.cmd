@echo off
setlocal
cd /d "%~dp0"
set "FROSTFALL_MODE="
if /i "%~1"=="--heist" set "FROSTFALL_MODE=--heist"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import panda3d.core" >nul 2>&1
    if not errorlevel 1 (
        ".venv\Scripts\python.exe" arena3d.py %FROSTFALL_MODE%
        goto finished
    )
)

py -3 -c "import panda3d.core" >nul 2>&1
if not errorlevel 1 (
    py -3 arena3d.py %FROSTFALL_MODE%
    goto finished
)

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*" "%USERPROFILE%\AppData\Local\Programs\Python\Python*") do (
    if exist "%%~fD\python.exe" (
        "%%~fD\python.exe" -c "import panda3d.core" >nul 2>&1
        if not errorlevel 1 (
            "%%~fD\python.exe" arena3d.py %FROSTFALL_MODE%
            goto finished
        )
    )
)

python -c "import panda3d.core" >nul 2>&1
if not errorlevel 1 (
    python arena3d.py %FROSTFALL_MODE%
    goto finished
)

echo Frostfall Arena 3D needs Python and Panda3D.
echo Install it with: py -m pip install -r requirements-3d.txt
pause
exit /b 1

:finished
if errorlevel 1 (
    echo Frostfall Arena 3D closed with an error.
    pause
    exit /b 1
)
exit /b 0
