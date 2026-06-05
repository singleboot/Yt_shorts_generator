@echo off
chcp 65001 >nul
title AI Shorts Creator - Web App
color 0A

echo ==========================================
echo   AI Shorts Creator - Starting Server...
echo ==========================================
echo.

REM Add local ffmpeg to PATH (overrides system ffmpeg)
set "PATH=%~dp0ffmpeg\bin;%PATH%"
where ffmpeg >nul 2>&1 && (echo [OK] ffmpeg: & ffmpeg -version 2>nul | findstr /R "ffmpeg version") || (echo [WARN] ffmpeg not found in local ffmpeg\bin)

REM Check if already running
for /f "tokens=2" %%a in ('tasklist /FI "WINDOWTITLE eq AI Shorts Creator - Web App*" /NH 2^>nul') do (
    echo [INFO] Server is already running!
    echo [INFO] Opening browser...
    start "" "http://127.0.0.1:8002"
    goto :end
)

REM Activate virtual environment and start server
set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%backend"

call "venv\Scripts\activate.bat"

REM Start uvicorn in background with window hidden, then open browser
start /min cmd /c "cd /d %PROJECT_DIR%backend && venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8002 --reload > webapp.log 2>&1"

echo [OK] Server started on http://127.0.0.1:8002
echo [INFO] Opening browser in 3 seconds...
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8002"

echo.
echo [DONE] AI Shorts Creator is running!
echo [INFO] To stop: run stop_app.bat
echo [INFO] Logs: backend/webapp.log
echo.

:end
pause
