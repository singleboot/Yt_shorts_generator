@echo off
setlocal enabledelayedexpansion
title AI Shorts Creator - Stop All
color 0C

echo ==========================================
echo   AI Shorts Creator - Stopping...
echo ==========================================
echo.

REM Try scheduled tasks first (cleanest shutdown)
schtasks /Query /TN "Backend_Shorts" >nul 2>&1
if !errorlevel!==0 (
    echo [INFO] Stopping Backend_Shorts scheduled task...
    schtasks /End /TN "Backend_Shorts" >nul 2>&1
)


REM Force-kill anything still bound to the ports
echo [INFO] Force-killing anything on port 8002 (backend)...
REM findstr regex: NO space (a space makes findstr treat it as OR)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R ":8002.*LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
    echo       killed PID %%a
)


echo.
echo [OK] All AI Shorts Creator processes stopped.
echo.
pause
endlocal
