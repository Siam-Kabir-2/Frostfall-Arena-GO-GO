@echo off
setlocal
cd /d "%~dp0"
for %%P in (".venv\Scripts\python.exe" "..\Frostfall Arena\.venv\Scripts\python.exe") do (
    if exist "%%~P" (
        "%%~P" -B -c "import panda3d.core" >nul 2>&1
        if not errorlevel 1 (
            "%%~P" -B gogo3d.py %*
            goto finished
        )
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
echo Install Panda3D with: python -m pip install -r requirements.txt
pause
exit /b 1

:finished
if errorlevel 1 (
    echo Frostfall Arena Go Go 3D closed with an error.
    pause
    exit /b 1
)
exit /b 0
