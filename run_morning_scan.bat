@echo off
REM Aristotle post-open flywheel scan (weekdays, ~9:40 AM ET = real prices).
REM Pure Python, no LLM. Scans the FULL watchlist (gameplan.json core+flex).
REM Pings Telegram only if a watchlist name is down >=3%.
cd /d "C:\Users\Ionai48q\.openclaw\workspaces\work\skills\aristotle-capital-flywheel"
python flash_check.py --scan --min -3 --notify >> scan_7am.log 2>&1
