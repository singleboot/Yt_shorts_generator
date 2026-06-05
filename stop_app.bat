@echo off
title AI Shorts Creator - Stop Server
color 0C

echo ==========================================
echo   AI Shorts Creator - Stopping Server...  
echo ==========================================
echo.

REM Kill uvicorn processes running on port 8002
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8002') do (
    echo [INFO] Stopping process PID: %%a
    taskkill /PID %%a /F >nul 2>&1
)

echo [OK] Server stopped.
echo.
pause
