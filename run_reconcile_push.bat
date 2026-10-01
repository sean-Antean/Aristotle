@echo off
REM Auto-push live reconciliation to Supabase -> keeps the Vercel dashboard fresh
REM and keeps the free-tier Supabase project from pausing.
REM Pure Python, no LLM tokens. Runs every 30 min during market hours (weekdays).
cd /d "C:\Users\Ionai48q\.openclaw\workspaces\work\skills\aristotle-capital-flywheel"
python reconcile.py --push >> reconcile_push.log 2>&1
