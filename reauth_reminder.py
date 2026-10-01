"""
Proactive Schwab re-auth reminder.
Schwab refresh tokens hard-expire ~7 days after a full auth. This pings Telegram
once the login is >=6 days old, so you re-auth BEFORE the 7 AM scan breaks -
instead of finding out after it already stopped working.

Reads last_reauth.txt (written by finish_auth.py / schwab_auth_manual.py on a full
re-auth; NOT touched by the daily access-token refresh). Pure Python, no LLM.
Scheduled daily via Windows Task "Aristotle Reauth Reminder".
"""
import pathlib
from datetime import datetime

import flash_check as fc  # reuse _telegram_send

HERE = pathlib.Path(__file__).parent
stamp = HERE / "last_reauth.txt"

try:
    last = datetime.fromisoformat(stamp.read_text().strip())
except Exception:
    print("[reminder] no valid last_reauth.txt - run schwab_auth_manual.py to set the baseline")
    raise SystemExit(0)

age_days = (datetime.now() - last).days
print(f"[reminder] Schwab login age: {age_days} days (hard limit ~7)")

if age_days >= 6:
    msg = (f"Aristotle: your Schwab login is {age_days} days old and expires around day 7. "
           f"Re-auth today so the live connection stays up. From anywhere on your phone, just "
           f"reply here with:  reauth  — I'll send you the link, you approve on Schwab and paste "
           f"the redirect URL back, and I'll finish it.")
    fc._telegram_send(msg)
    print("[reminder] Telegram reminder sent")
else:
    print("[reminder] still fresh - no ping")
