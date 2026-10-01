"""
supabase_sync.py — push a reconciliation snapshot to Supabase (for the dashboard)
=================================================================================
Pure Python REST call (no LLM, no heavy deps). Reads local `supabase_config.json`:

    { "url": "https://xxxx.supabase.co", "service_role_key": "eyJ..." }

Keep that file local and OUT of git — the service role key is a full-access secret.
Called by `python reconcile.py --push`.
"""

import json
import urllib.request
from pathlib import Path

from schwab_bridge import get_ssl_context

CONFIG = Path(__file__).parent / "supabase_config.json"


def _cfg():
    if not CONFIG.exists():
        return None
    try:
        return json.loads(CONFIG.read_text())
    except Exception:
        return None


def push_snapshot(payload):
    """Insert one snapshot row. Returns True on success."""
    cfg = _cfg()
    if not cfg or not cfg.get("url") or not cfg.get("service_role_key"):
        print("[WARN] supabase_config.json missing url/service_role_key — skipping push.")
        return False

    snap = payload.get("snapshot", {})
    # Guard: never overwrite the dashboard with an empty/failed snapshot. Transient
    # Schwab API failures can return 0 accounts / $0 net liq; pushing that would clobber
    # the last good data. Only push snapshots that actually have accounts and value.
    if not snap.get("accounts") or not snap.get("combined_net_liq"):
        print("[SKIP] empty snapshot (0 accounts / $0 net liq) - likely a transient "
              "Schwab failure; NOT pushing (dashboard keeps its last good data).")
        return False

    guards = payload.get("guardrails", [])
    row = {
        "as_of": snap.get("as_of"),
        "combined_net_liq": snap.get("combined_net_liq"),
        "deployed_pct": snap.get("deployed_pct"),
        "cash_reserve_pct": snap.get("cash_reserve_pct"),
        "fail_count": sum(1 for g in guards if g.get("status") == "FAIL"),
        "warn_count": sum(1 for g in guards if g.get("status") == "WARN"),
        "action_count": len(payload.get("action_items", [])),
        "payload": payload,
    }

    req = urllib.request.Request(
        cfg["url"].rstrip("/") + "/rest/v1/snapshots",
        data=json.dumps(row, default=str).encode(),
        method="POST",
        headers={
            "apikey": cfg["service_role_key"],
            "Authorization": f"Bearer {cfg['service_role_key']}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    try:
        with urllib.request.urlopen(req, context=get_ssl_context()) as r:
            if r.status in (200, 201, 204):
                print("[OK] Snapshot pushed to Supabase.")
                return True
            print(f"[WARN] Supabase returned status {r.status}")
            return False
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode(errors="replace")[:300]
        except Exception:
            pass
        print(f"[ERROR] Supabase push failed: HTTP {e.code} {body}")
        return False
    except Exception as e:
        print(f"[ERROR] Supabase push failed: {e}")
        return False
