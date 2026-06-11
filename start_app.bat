@echo off
chcp 65001 >nul
title AI Shorts Creator - Web App
color 0A

REM Use delayed expansion so set-inside-for is visible to the if that follows
setlocal enabledelayedexpansion

echo ==========================================
echo   AI Shorts Creator - Starting...
echo ==========================================
echo.

REM Add local ffmpeg to PATH (overrides system ffmpeg)
set "PATH=%~dp0ffmpeg\bin;%PATH%"
where ffmpeg >nul 2>&1 && (echo [OK] ffmpeg: & ffmpeg -version 2>nul | findstr /R "ffmpeg version") || (echo [WARN] ffmpeg not found in local ffmpeg\bin)

REM ---------------------------------------------------------------------------
REM 1. Check if Backend is already running on port 8002
REM ---------------------------------------------------------------------------
set "BACKEND_RUNNING=0"
set "BACKEND_PID="
REM findstr regex: NO space between :8002 and :8002.*LISTENING (a space makes findstr treat it as OR)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R ":8002.*LISTENING"') do (
    set "BACKEND_RUNNING=1"
    set "BACKEND_PID=%%a"
)

REM ---------------------------------------------------------------------------
REM 2. Check if ComfyUI is already running on port 8188
REM ---------------------------------------------------------------------------
set "COMFYUI_RUNNING=0"
set "COMFYUI_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R ":8188.*LISTENING"') do (
    set "COMFYUI_RUNNING=1"
    set "COMFYUI_PID=%%a"
)

REM Sanity: if both ports report the SAME PID it's a parsing error - reset both
if "!BACKEND_RUNNING!"=="1" if "!COMFYUI_RUNNING!"=="1" if "!BACKEND_PID!"=="!COMFYUI_PID!" (
    echo [WARN] Parsing error: both ports report same PID. Re-checking...
    set "BACKEND_RUNNING=0"
    set "BACKEND_PID="
    set "COMFYUI_RUNNING=0"
    set "COMFYUI_PID="
)

if "!BACKEND_RUNNING!"=="1" (
    echo [INFO] Backend already running on port 8002 ^(PID !BACKEND_PID!^)
) else (
    echo [INFO] Backend not running, starting...
    set "PROJECT_DIR=%~dp0"
    cd /d "!PROJECT_DIR!backend"
    call "venv\Scripts\activate.bat" 2>nul
    REM Start uvicorn in a hidden window, log to webapp.log
    start /min "uvicorn" cmd /c "cd /d !PROJECT_DIR!backend && set PYTHONUTF8=1&& venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002 > webapp.log 2>&1"
    echo [OK] Backend started ^(logs: backend\webapp.log^)
    cd /d "%~dp0"
)

if "!COMFYUI_RUNNING!"=="1" (
    echo [INFO] ComfyUI already running on port 8188 ^(PID !COMFYUI_PID!^)
) else (
    echo [INFO] ComfyUI not running, starting...
    REM Try scheduled task first
    schtasks /Query /TN "ComfyUI" >nul 2>&1
    if !errorlevel!==0 (
        schtasks /Run /TN "ComfyUI"
        echo [OK] ComfyUI started via scheduled task
    ) else (
        echo [WARN] ComfyUI scheduled task not found - start it manually from Settings
    )
)

REM ---------------------------------------------------------------------------
REM 3. Wait for backend to be ready, then open browser
REM ---------------------------------------------------------------------------
echo.
echo [INFO] Waiting for backend on http://127.0.0.1:8002 ...
set /a RETRIES=0
:wait_loop
if !RETRIES! GEQ 30 goto :wait_done
set /a RETRIES+=1
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:8002/api/health' -UseBasicParsing -TimeoutSec 2).StatusCode } catch { exit 1 }" >nul 2>&1
if !errorlevel!==0 goto :ready
timeout /t 1 /nobreak >nul
goto :wait_loop

:ready
echo [OK] Backend is ready!
start "" "http://127.0.0.1:8002"
echo [OK] Browser opened.
goto :done

:wait_done
echo [WARN] Backend did not respond within 30 seconds. Check backend\webapp.log

:done
echo.
echo ==========================================
echo   AI Shorts Creator is running
echo ==========================================
echo [URL]  http://127.0.0.1:8002
echo [LOG]  backend\webapp.log
echo [STOP] Run stop_app.bat
echo ==========================================
echo.
pause
endlocal
