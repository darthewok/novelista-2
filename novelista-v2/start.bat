@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ---- 1. find Python 3.11+ ----
set PY=
for %%C in ("py -3.11" "py -3.12" "py -3.13" "py -3.14" "py -3" "python") do (
    if not defined PY (
        %%~C -c "import sys;sys.exit(sys.version_info<(3,11))" >nul 2>&1
        if not errorlevel 1 set PY=%%~C
    )
)
if not defined PY (
    echo [novelista] Novelista needs Python 3.11 or newer. Install it from python.org, then run this again.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('!PY! --version 2^>^&1') do echo [novelista] using %%v

REM ---- 2. virtual environment + dependencies ----
set VPY=backend\.venv\Scripts\python.exe
set MARK=backend\.venv\.installed
set NEED=0
if not exist "%VPY%" (
    echo [novelista] first-time setup: creating environment...
    !PY! -m venv backend\.venv
    if errorlevel 1 goto :setupfail
    set NEED=1
)
if not exist "%MARK%" set NEED=1
if "!NEED!"=="0" (
    REM reinstall if requirements.txt is newer than the marker
    for /f %%r in ('powershell -NoProfile -Command "if ((Get-Item 'backend\requirements.txt').LastWriteTime -gt (Get-Item '%MARK%').LastWriteTime) {1} else {0}"') do set NEED=%%r
)
if "!NEED!"=="1" (
    echo [novelista] first-time setup: installing components, this takes a minute...
    "%VPY%" -m pip install -q --disable-pip-version-check -r backend\requirements.txt
    if errorlevel 1 goto :setupfail
    echo ok> "%MARK%"
)

REM ---- 3. pick a port ----
if not exist ".run" mkdir ".run"
set PORT=
for /l %%p in (8000,1,8010) do (
    if not defined PORT (
        netstat -ano | findstr /R /C:":%%p .*LISTENING" >nul
        if errorlevel 1 set PORT=%%p
    )
)
if not defined PORT (
    echo [novelista] ports 8000-8010 are all in use. Close other programs and try again.
    pause
    exit /b 1
)
echo [novelista] using port !PORT!

REM ---- 4. start the server (minimised) ----
del /q ".run\pid" ".run\port" 2>nul
echo !PORT!> ".run\port"
pushd backend
start "Novelista Server" /min cmd /c ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port !PORT! > ..\.run\server.log 2>&1"
popd
echo [novelista] starting server...

REM ---- 5. wait for health ----
set READY=0
for /l %%i in (1,1,30) do (
    if "!READY!"=="0" (
        set CODE=
        for /f %%c in ('curl -s -o nul -w "%%{http_code}" http://127.0.0.1:!PORT!/api/health 2^>nul') do set CODE=%%c
        if "!CODE!"=="200" (set READY=1) else timeout /t 1 /nobreak >nul
    )
)
if "!READY!"=="1" (
    echo [novelista] ready
) else (
    echo [novelista] did not respond in 30s - check .run\server.log
    pause
    exit /b 1
)

REM ---- 6. open the browser ----
REM record the server PID from the port listener (stop.bat also sweeps by port)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":!PORT! .*LISTENING"') do if not "%%p"=="0" echo %%p> ".run\pid"
echo [novelista] opening http://127.0.0.1:!PORT!
start "" "http://127.0.0.1:!PORT!"
endlocal
exit /b 0

:setupfail
echo [novelista] setup failed. Check your internet connection and run this again.
pause
exit /b 1
