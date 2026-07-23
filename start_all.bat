@echo off
cd /d "%~dp0"

echo ==========================================
echo Starting Web Health Checker...
echo ==========================================

if exist "venv\Scripts\python.exe" (
    set PYTHON=venv\Scripts\python.exe
) else (
    set PYTHON=python
)

echo.
echo [1/2] Starting Django Server...
start "Django Server" cmd /k "%PYTHON% manage.py runserver"

echo [2/2] Starting Background Monitor...
start "Health Monitor" cmd /k "%PYTHON% background_monitor.py"

echo.
echo Both services are starting.
echo - Dashboard:  http://127.0.0.1:8000
echo - Monitoring: every 5 minutes (Health Monitor window)
echo.
echo Keep BOTH windows open. Close them to stop.
echo.
pause




#.\start_all.bat
