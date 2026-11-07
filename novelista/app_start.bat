@echo off
setlocal enabledelayedexpansion

REM ===== Novelista launcher =====
REM Starts Ollama (if absent), FastAPI backend, Next.js frontend, and opens the dashboard.
REM Child PIDs are recorded in .run\pids.txt so app_stop.bat can terminate them cleanly.

set ROOT=%~dp0
if "%ROOT:~-1%"=="\" set ROOT=%ROOT:~0,-1%
cd /d "%ROOT%"

if not exist ".run" mkdir ".run"
del /q ".run\pids.txt" 2>nul

echo [novelista] checking Ollama...
tasklist /FI "IMAGENAME eq ollama.exe" 2>nul | find /I "ollama.exe" >nul
if errorlevel 1 (
    echo [novelista] starting Ollama...
    start "" "ollama" serve
    REM Give Ollama a couple of seconds to listen.
    timeout /t 2 /nobreak >nul
) else (
    echo [novelista] Ollama already running.
)

echo [novelista] starting backend on :8000 ...
pushd "%ROOT%\backend"
start "Novelista Backend" /min cmd /c ".venv\Scripts\activate && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
popd

REM Capture the backend's parent cmd.exe PID (best-effort; window-title kill covers the rest).
for /f "tokens=2 delims=," %%p in ('tasklist /V /FO CSV /NH ^| findstr /C:"Novelista Backend"') do (
    echo %%~p>> ".run\pids.txt"
)

echo [novelista] starting frontend on :3000 ...
pushd "%ROOT%\frontend"
start "Novelista Frontend" /min cmd /c "npm run start"
popd

for /f "tokens=2 delims=," %%p in ('tasklist /V /FO CSV /NH ^| findstr /C:"Novelista Frontend"') do (
    echo %%~p>> ".run\pids.txt"
)

echo [novelista] waiting for the frontend to be ready ...
set READY=0
for /l %%i in (1,1,30) do (
    if !READY!==1 goto :ready
    curl -s -o nul -w "%%{http_code}" http://127.0.0.1:3000 > "%TEMP%\nv_status.txt" 2>nul
    set /p STATUS=<"%TEMP%\nv_status.txt"
    if "!STATUS!"=="200" set READY=1
    if "!STATUS!"=="307" set READY=1
    if "!STATUS!"=="308" set READY=1
    timeout /t 1 /nobreak >nul
)

:ready
if !READY!==0 (
    echo [novelista] frontend did not respond within 30s. Opening anyway ^(it may still be compiling^).
) else (
    echo [novelista] frontend is up.
)

start "" "http://127.0.0.1:3000"
echo [novelista] ready. Use app_stop.bat to shut down.

endlocal
