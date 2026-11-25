@echo off
setlocal
cd /d "%~dp0"
for %%P in (".venv\Scripts\python.exe") do (
    if exist "%%~P" (
        "%%~P" -B -c "import pygame" >nul 2>&1
        if not errorlevel 1 (
            "%%~P" -B gogo.py %*
            goto finished
        )
    )
)
py -3 -B -c "import pygame" >nul 2>&1
if not errorlevel 1 (
    py -3 -B gogo.py %*
    goto finished
)
python -B -c "import pygame" >nul 2>&1
if not errorlevel 1 (
    python -B gogo.py %*
    goto finished
)
echo Frostfall Go Go needs Python and Pygame.
echo Install Pygame with: python -m pip install -r requirements.txt
pause
exit /b 1

:finished
if errorlevel 1 (
    echo Frostfall Go Go closed with an error.
    pause
    exit /b 1
)
exit /b 0
