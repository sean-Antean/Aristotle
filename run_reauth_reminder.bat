@echo off
REM Daily proactive Schwab re-auth reminder. Pings Telegram once the login is
REM >=6 days old (Schwab tokens hard-expire ~7 days). Pure Python, no LLM.
cd /d "C:\Users\Ionai48q\.openclaw\workspaces\work\skills\aristotle-capital-flywheel"
python reauth_reminder.py >> reauth_reminder.log 2>&1
