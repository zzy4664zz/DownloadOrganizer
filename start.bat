@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys, tkinter; assert sys.version_info >= (3, 12)" >nul 2>nul
    if not errorlevel 1 (
        py -3 main.py %*
        if errorlevel 1 (
            pause
            exit /b 1
        )
        exit /b 0
    )
)
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys, tkinter; assert sys.version_info >= (3, 12)" >nul 2>nul
    if not errorlevel 1 (
        python main.py %*
        if errorlevel 1 (
            pause
            exit /b 1
        )
        exit /b 0
    )
)
echo Python 3.12+ with Tcl/Tk was not found.
echo Install Python from https://www.python.org/downloads/windows/
echo Or download DownloadOrganizer.exe from this repository's GitHub Releases.
pause
exit /b 1
