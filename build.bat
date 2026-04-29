@echo off
setlocal enabledelayedexpansion

REM MathCore build script -- produces a portable distributable in dist\MathCore.
REM Requires: Python 3.11+ and Node.js 18+ on PATH.

set ROOT=%~dp0
cd /d "%ROOT%"

echo ============================================
echo  MathCore build script
echo ============================================
echo.

REM ---- Precheck: Python ------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not on PATH.
    echo.
    echo Install Python 3.11 or newer from https://www.python.org/downloads/
    echo and tick "Add python.exe to PATH" during the installer.
    goto :fail
)

REM ---- Precheck: Node / npm --------------------------------------------------
where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js / npm is not on PATH.
    echo.
    echo The frontend is built with Vite, which needs Node.js 18 or newer.
    echo Install it from https://nodejs.org/  ^(LTS is fine^), reopen this
    echo window so PATH refreshes, then run build.bat again.
    goto :fail
)

REM ---- Step 1: virtualenv ----------------------------------------------------
if not exist "venv" (
    echo [1/5] Creating local virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtualenv. Is Python 3.11+ installed?
        goto :fail
    )
) else (
    echo [1/5] Virtual environment already present.
)

REM ---- Step 2: Python deps ---------------------------------------------------
echo [2/5] Installing Python dependencies...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install Python dependencies.
    goto :fail
)

REM ---- Step 3: npm install ---------------------------------------------------
echo [3/5] Installing frontend dependencies...
pushd frontend
if not exist "node_modules" (
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        popd
        goto :fail
    )
)

REM ---- Step 4: Vite build ----------------------------------------------------
echo [4/5] Building frontend (Vite)...
call npm run build
if errorlevel 1 (
    echo [ERROR] Frontend build failed.
    popd
    goto :fail
)
popd

REM Move the frontend build output into a location relative to the launcher
if exist "static" rmdir /s /q "static"
xcopy /E /I /Y "frontend\dist" "static" >nul

REM ---- Step 5: PyInstaller ---------------------------------------------------
echo [5/5] Packaging with PyInstaller...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

python -m PyInstaller mathcore.spec --clean --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed.
    goto :fail
)

REM Assemble the portable folder
set DIST=dist\Aegis2
if exist "%DIST%\data" rmdir /s /q "%DIST%\data"
xcopy /E /I /Y "data" "%DIST%\data" >nul
copy /Y "README.txt" "%DIST%\README.txt" >nul

echo.
echo ============================================
echo  Build complete.
echo  Portable folder:  %DIST%
echo  Launcher:         %DIST%\Aegis2.exe
echo ============================================
echo.
pause
endlocal
exit /b 0

:fail
echo.
echo ============================================
echo  Build FAILED. See message above for details.
echo ============================================
echo.
pause
endlocal
exit /b 1
