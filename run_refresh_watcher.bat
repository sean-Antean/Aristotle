@echo off
cd /d "%~dp0"
python refresh_watcher.py >> refresh_watcher.log 2>&1
