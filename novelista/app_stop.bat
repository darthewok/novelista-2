@echo off
setlocal enabledelayedexpansion

REM ===== Novelista shutdown =====
REM Kills the backend + frontend. Pass `--full` to also stop Ollama.

set ROOT=%~dp0
if "%ROOT:~-1%"=="\" set ROOT=%ROOT:~0,-1%
cd /d "%ROOT%"

set KILL_OLLAMA=0
if /I "%~1"=="--full" set KILL_OLLAMA=1

echo [novelista] stopping frontend + backend ...

REM 1) Best-effort: terminate recorded PIDs (graceful first, then force).
if exist ".run\pids.txt" (
    for /f "tokens=*" %%p in (.run\pids.txt) do (
        taskkill /PID %%p /T >nul 2>&1
    )
    timeout /t 1 /nobreak >nul
    for /f "tokens=*" %%p in (.run\pids.txt) do (
        taskkill /PID %%p /T /F >nul 2>&1
    )
)

REM 2) Window-title fallback for any survivors.
taskkill /FI "WINDOWTITLE eq Novelista Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Novelista Frontend*" /T /F >nul 2>&1

REM 3) Port-based sweep in case titles changed — kill whatever holds :8000 and :3000.
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:"LISTENING.*:8000 " 2^>nul') do (
    if not "%%p"=="0" taskkill /PID %%p /F >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:"LISTENING.*:3000 " 2^>nul') do (
    if not "%%p"=="0" taskkill /PID %%p /F >nul 2>&1
)

if !KILL_OLLAMA!==1 (
    echo [novelista] stopping Ollama ...
    taskkill /IM ollama.exe /F >nul 2>&1
) else (
    echo [novelista] Ollama left running ^(pass --full to stop it too^).
)

if exist ".run\pids.txt" del /q ".run\pids.txt"

echo [novelista] stopped.
endlocal
