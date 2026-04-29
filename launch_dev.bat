@echo off
setlocal

REM Run MathCore from source using the project venv.
REM Does NOT need Node.js -- if static\ is missing, the backend serves a
REM placeholder page reminding you to build the frontend.

set ROOT=%~dp0
cd /d "%ROOT%"

if not exist "venv\Scripts\python.exe" (
    echo ============================================
    echo  Virtual environment not found.
    echo  Run build.bat first, or set it up manually:
    echo      python -m venv venv
    echo      venv\Scripts\activate
    echo      pip install -r requirements.txt
    echo ============================================
    pause
    exit /b 1
)

echo Starting MathCore (dev mode, from source)...
echo Close this window to stop the app.
echo.

venv\Scripts\python.exe launcher.py
set EXITCODE=%ERRORLEVEL%

if not %EXITCODE%==0 (
    echo.
    echo MathCore exited with code %EXITCODE%.
    pause
)

endlocal
exit /b %EXITCODE%
