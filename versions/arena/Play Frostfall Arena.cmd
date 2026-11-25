@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import pygame" >nul 2>&1
    if not errorlevel 1 (
        ".venv\Scripts\python.exe" main.py
        goto finished
    )
)

py -3 -c "import pygame" >nul 2>&1
if not errorlevel 1 (
    py -3 main.py
    goto finished
)

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*" "%USERPROFILE%\AppData\Local\Programs\Python\Python*") do (
    if exist "%%~fD\python.exe" (
        "%%~fD\python.exe" -c "import pygame" >nul 2>&1
        if not errorlevel 1 (
            "%%~fD\python.exe" main.py
            goto finished
        )
    )
)

python -c "import pygame" >nul 2>&1
if not errorlevel 1 (
    python main.py
    goto finished
)

echo Frostfall Arena needs Python 3.11 or newer with Pygame installed.
echo Run python -m pip install -r requirements.txt using your Windows Python.
pause
exit /b 1

:finished
if errorlevel 1 (
    echo Frostfall Arena closed with an error.
    pause
    exit /b 1
)
exit /b 0
