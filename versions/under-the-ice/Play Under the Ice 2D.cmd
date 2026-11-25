@echo off
setlocal
cd /d "%~dp0"
for %%P in (".venv\Scripts\python.exe") do (
    if exist "%%~P" (
        "%%~P" -B -c "import pygame" >nul 2>&1
        if not errorlevel 1 (
            "%%~P" -B under_the_ice.py %*
            goto finished
        )
    )
)
py -3 -B -c "import pygame" >nul 2>&1
if not errorlevel 1 (
    py -3 -B under_the_ice.py %*
    goto finished
)
python -B -c "import pygame" >nul 2>&1
if not errorlevel 1 (
    python -B under_the_ice.py %*
    goto finished
)
echo Under the Ice needs Python 3 and Pygame.
echo Install it with: python -m pip install -r requirements.txt
pause
exit /b 1

:finished
if errorlevel 1 (
    echo Under the Ice closed with an error.
    pause
    exit /b 1
)
exit /b 0
