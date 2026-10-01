@echo off
echo ==========================================
echo Aristotle Capital Flywheel - Setup
echo ==========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found. Please install Python 3.8+
    exit /b 1
)

echo ✅ Python found

REM Create directories
if not exist analysis mkdir analysis
if not exist logs mkdir logs

echo ✅ Directories created

REM Run setup
echo.
echo 🔧 Configure Schwab API
echo ---------------------------
python schwab_bridge.py --setup

echo.
echo ==========================================
echo Setup Complete!
echo ==========================================
echo.
echo Next steps:
echo 1. Run: python schwab_auth.py
echo 2. Login to Schwab in browser
echo 3. Authorize the app
echo 4. Test: python schwab_bridge.py --quotes TSLL
echo.
pause
