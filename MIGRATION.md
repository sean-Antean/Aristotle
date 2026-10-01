# Aristotle Capital Flywheel — Migration Guide

How to stand this project up on a new machine or under a new Claude account.
Last migrated: 2026-10-01.

## What this repo is
A gated **cash-secured-put "wheel"** toolset for two live Schwab IRAs: a Python
engine (`execute.py`, `reconcile.py`, `flash_check.py`, `pacing.py`,
`schwab_bridge.py`, `schwab_accounts.py`), a Next.js/Vercel + Supabase dashboard
(`dashboard/`), and Windows automation (`run_*.bat`, `*.vbs`).

> **`execute.py` is the only module that places orders.** It is triple-gated
> (master switch + confirm token + PIN). A human places every order — the agent
> stages tickets only, and never arms live trading. See `ARISTOTLE_INSTRUCTIONS.md`
> and `SECURITY` notes before touching it.

## 🔑 Secrets are NOT in git
This repo is intentionally scrubbed of credentials. The following are **git-ignored**
and travel **only** in the separate `Aristotle-migration.zip` (never committed, never
pushed). Drop them into the repo root (and `dashboard/`) after cloning:

| File | Purpose |
|---|---|
| `schwab_config.json` | Schwab API client id/secret |
| `schwab_tokens.json` | Live Schwab OAuth tokens (expire ~7 days — re-auth after) |
| `execution_auth.json` | PBKDF2 PIN hash for the live-order gate |
| `supabase_config.json` | Supabase URL + service key (reconcile → dashboard) |
| `telegram_config.json` | Telegram bot token + chat id (alerts) |
| `vercel-recovery-codes.txt` | Vercel account recovery codes |
| `auth_code.txt` | Scratch OAuth code (disposable) |
| `txns_45d.json` | Cached transactions (disposable) |
| `dashboard/.env.local` | Dashboard Supabase keys |

Example templates (`supabase_config.example.json`, `dashboard/.env.local.example`)
ARE committed — use them if you ever need to rebuild a secret from scratch.

## Setup on the new machine / account
1. **Clone:** `git clone https://github.com/sean-Antean/Aristotle.git`
2. **Restore secrets:** unzip `Aristotle-migration.zip` and copy the files in the
   table above into the matching locations (root + `dashboard/`).
3. **Python:** Python 3.11+. Install deps as needed:
   `pip install requests` (plus anything your scripts import). No `requirements.txt`
   yet — add one if you want reproducible installs.
4. **Re-auth Schwab** (tokens expire ~weekly):
   `python generate_auth_url.py` → open the URL → log in → paste the callback URL into
   `python exchange_code.py "<callback-url>"`. Confirm with `python reconcile.py`.
5. **Dashboard (optional):** `cd dashboard && npm install && npm run dev`
   (deploy with `vercel`). Needs `dashboard/.env.local`.
6. **Automation (optional, Windows):** re-register the Task Scheduler jobs that call
   `run_refresh_watcher.bat`, `run_reconcile_push.bat`, `run_reauth_reminder.bat`,
   `run_morning_scan.bat`, `run_trend_watch.bat`. Paths inside the `.bat`/`.vbs`
   files are machine-specific — update them to the new clone location.

## Safety invariants (do not break)
- Secrets stay git-ignored. Never `git add -A` without checking `git status` first.
- `enabled_live` is armed only by a deliberate human desk edit — never by an agent,
  never over Telegram. The agent can only disarm.
- The PIN is never typed into chat. Re-auth/exchange is done by the human.
