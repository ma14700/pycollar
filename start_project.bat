@echo off
SETLOCAL

set PROJECT_ROOT=%~dp0
cd /d "%PROJECT_ROOT%"

echo ===================================================
echo      Starting PyCollar Trading System
echo ===================================================

:: Check if server directory exists
if not exist "server" (
    echo Error: 'server' directory not found.
    pause
    exit /b 1
)

:: Check if web directory exists
if not exist "web" (
    echo Error: 'web' directory not found.
    pause
    exit /b 1
)

echo.
echo [1/2] Launching Backend (FastAPI)...
:: Starts uvicorn in a new window. Using python -m uvicorn is generally safer.
start "PyCollar Backend" cmd /k "cd /d %PROJECT_ROOT%server && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"

echo.
echo [2/2] Launching Frontend (React/Vite)...
:: Starts npm run dev in a new window.
start "PyCollar Frontend" cmd /k "cd /d %PROJECT_ROOT%web && npm run dev"

echo.
echo ===================================================
echo      Services are starting in new windows.
echo      Backend API: http://localhost:8000
echo      Frontend UI: http://localhost:5173
echo ===================================================
echo.

:: Optional: Wait a bit and open browser
timeout /t 5 >nul
start http://localhost:5173

ENDLOCAL
