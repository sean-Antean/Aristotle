"""On-demand refresh watcher.

Polls Supabase `control.refresh_requested_at`. If a refresh was requested more
recently than the last snapshot we pushed, run `reconcile.py --push` so the
dashboard's "Refresh now" button triggers a genuine fresh Schwab pull.

Runs every minute via Windows Task Scheduler during market hours. Pure Python,
zero LLM tokens. One-shot: checks, acts if needed, exits.
"""
import json
import pathlib
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
from schwab_bridge import get_ssl_context  # noqa: E402

CFG = json.loads((HERE / "supabase_config.json").read_text())
BASE = CFG["url"].rstrip("/") + "/rest/v1/"
KEY = CFG.get("service_role_key") or CFG.get("key")
HEADERS = {"apikey": KEY, "Authorization": f"Bearer {KEY}"}


def sb_get(path):
    req = urllib.request.Request(BASE + path, headers=HEADERS)
    with urllib.request.urlopen(req, context=get_ssl_context(), timeout=20) as r:
        return json.loads(r.read().decode())


def parse(t):
    if not t:
        return None
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        return None


def main():
    try:
        ctrl = sb_get("control?id=eq.1&select=refresh_requested_at")
        snaps = sb_get("snapshots?select=created_at&order=created_at.desc&limit=1")
    except Exception as e:  # network/paused project — nothing to do this tick
        print(f"[watcher] supabase read failed: {e}")
        return

    req_at = parse(ctrl[0]["refresh_requested_at"]) if ctrl else None
    snap_at = parse(snaps[0]["created_at"]) if snaps else None
    now = datetime.now(timezone.utc)

    if req_at is None:
        print("[watcher] no request on file")
        return

    # Fulfill only if the request is newer than our latest snapshot, and recent
    # (< 5 min old) so a stale flag can't loop-trigger pushes.
    age_min = (now - req_at).total_seconds() / 60
    if age_min > 5:
        print(f"[watcher] request is {age_min:.1f} min old — ignoring")
        return
    if snap_at is not None and req_at <= snap_at:
        print("[watcher] already fulfilled")
        return

    print(f"[watcher] refresh requested {age_min:.1f} min ago -> pushing")
    subprocess.run([sys.executable, str(HERE / "reconcile.py"), "--push"], cwd=str(HERE))


if __name__ == "__main__":
    main()
