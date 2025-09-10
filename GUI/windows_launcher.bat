@echo off
REM xsukax RSS Search - Windows Launcher
REM ===================================
REM 
REM Simple batch file to launch the RSS search GUI on Windows
REM Handles Python detection and provides helpful error messages

title xsukax RSS Search

echo.
echo ================================================
echo xsukax RSS Search - Windows Launcher
echo ================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH
    echo.
    echo Please install Python 3.6 or higher from:
    echo https://www.python.org/downloads/
    echo.
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

REM Display Python version
echo Checking Python installation...
python --version

REM Check if launcher script exists
if not exist "launcher.py" (
    echo.
    echo Error: launcher.py not found!
    echo Please ensure all files are in the same directory.
    echo.
    pause
    exit /b 1
)

REM Launch the application
echo.
echo Starting application...
python launcher.py

REM If we get here, the application has closed
echo.
echo Application closed.
pause
