@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set PORT=8000
if exist ".run\port" set /p PORT=<".run\port"

echo [novelista] stopping server...
if exist ".run\pid" (
    set /p SPID=<".run\pid"
    taskkill /PID !SPID! /T /F >nul 2>&1
)

REM fallback: anything still listening on the port
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":!PORT! .*LISTENING"') do (
    if not "%%p"=="0" taskkill /PID %%p /T /F >nul 2>&1
)

if /I "%~1"=="--full" (
    echo [novelista] stopping Ollama...
    taskkill /IM ollama.exe /F >nul 2>&1
    echo [novelista] If you use LM Studio, close it from its own window.
)

del /q ".run\pid" ".run\port" 2>nul
echo [novelista] stopped
endlocal
