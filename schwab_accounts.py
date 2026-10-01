"""
Schwab Trader API - Read-only account layer for Aristotle v4.0
==============================================================
This is the piece that was MISSING. schwab_bridge.py only spoke to the
Market Data API (quotes/chains/history). This module speaks to the
Trader API so Aristotle can finally SEE the live accounts:

    accounts / balances / positions / orders / transactions

READ-ONLY BY DESIGN. There is intentionally no order-placement function
here. Aristotle is advisory-only on live retirement money.

Reuses OAuth/token handling from schwab_bridge.py (single token store).

Usage:
    python schwab_accounts.py --numbers          # account# -> hash map (masks)
    python schwab_accounts.py --accounts         # balances + positions (both IRAs)
    python schwab_accounts.py --positions        # flattened option/share positions
    python schwab_accounts.py --orders --days 14 # working + filled orders
    python schwab_accounts.py --transactions --days 30
"""

import json
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Reuse token handling / config from the existing bridge (single source of auth).
from schwab_bridge import get_access_token, BASE_URL, get_ssl_context

TRADER_API_URL = f"{BASE_URL}/trader/v1"
CONFIG_DIR = Path(__file__).parent
GAMEPLAN_FILE = CONFIG_DIR / "gameplan.json"
STATE_DIR = CONFIG_DIR / "state"


# --------------------------------------------------------------------------- #
# Low-level authenticated GET against the Trader API
# --------------------------------------------------------------------------- #
def _trader_get(path, params=None):
    """Authenticated GET against the Trader API. Returns parsed JSON or None."""
    token = get_access_token()
    if not token:
        print("[ERROR] No valid access token. Re-run schwab authentication.")
        return None

    url = f"{TRADER_API_URL}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    ctx = get_ssl_context()
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode()
        except Exception:
            pass
        print(f"[ERROR] Trader API {e.code} {e.reason} on /{path}")
        if e.code == 401:
            print("   Token expired/invalid -> re-authenticate.")
        elif e.code == 403:
            print("   403 Forbidden -> your Schwab app likely lacks the")
            print("   'Accounts and Trading' scope. Re-create/authorize the app")
            print("   with account access enabled, then re-run auth.")
        if body:
            print(f"   Detail: {body[:300]}")
        return None
    except Exception as e:
        print(f"[ERROR] Trader request failed: {e}")
        return None


# --------------------------------------------------------------------------- #
# Account discovery (number <-> hash) + masks from gameplan
# --------------------------------------------------------------------------- #
def load_gameplan():
    if GAMEPLAN_FILE.exists():
        with open(GAMEPLAN_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def get_account_numbers():
    """
    Map plain account numbers to the encrypted hashes the API requires.
    Returns list of {accountNumber, hashValue, mask, label}.
    """
    data = _trader_get("accounts/accountNumbers")
    if not data:
        return []

    gp = load_gameplan()
    label_by_mask = {}
    for a in gp.get("accounts", []):
        label_by_mask[str(a.get("mask"))] = a
    out = []
    for item in data:
        acct = str(item.get("accountNumber", ""))
        mask = acct[-3:] if len(acct) >= 3 else acct
        meta = label_by_mask.get(mask, {})
        out.append({
            "accountNumber": acct,
            "hashValue": item.get("hashValue"),
            "mask": mask,
            "label": meta.get("label", mask),
            "type": meta.get("type", "Unknown"),
        })
    return out


# --------------------------------------------------------------------------- #
# Accounts: balances + positions
# --------------------------------------------------------------------------- #
def get_accounts(include_positions=True):
    """All accounts with balances and (optionally) positions."""
    params = {"fields": "positions"} if include_positions else None
    return _trader_get("accounts", params)


def _summarize_account(acct_obj):
    """Pull the fields Aristotle cares about out of one securitiesAccount block."""
    sa = acct_obj.get("securitiesAccount", acct_obj)
    bals = sa.get("currentBalances", {})
    acct_num = str(sa.get("accountNumber", ""))
    mask = acct_num[-3:] if len(acct_num) >= 3 else acct_num

    # Net liq: naming differs across account types; try the common fields.
    net_liq = (bals.get("liquidationValue")
               or bals.get("equity")
               or bals.get("accountValue"))
    cash = (bals.get("cashBalance")
            or bals.get("cashAvailableForTrading")
            or bals.get("totalCash"))
    buying_power = (bals.get("buyingPower")
                    or bals.get("cashAvailableForTrading"))

    positions = []
    for p in sa.get("positions", []):
        instr = p.get("instrument", {})
        long_qty = p.get("longQuantity", 0) or 0
        short_qty = p.get("shortQuantity", 0) or 0
        qty = long_qty - short_qty  # negative = short
        positions.append({
            "symbol": instr.get("symbol"),
            "underlying": instr.get("underlyingSymbol"),
            "assetType": instr.get("assetType"),
            "putCall": instr.get("putCall"),
            "quantity": qty,
            "long_qty": long_qty,
            "short_qty": short_qty,
            "average_price": p.get("averagePrice"),
            "market_value": p.get("marketValue"),
            "description": instr.get("description"),
        })

    return {
        "mask": mask,
        "account_number": acct_num,
        "type": sa.get("type"),
        "net_liq": net_liq,
        "cash": cash,
        "buying_power": buying_power,
        "positions": positions,
    }


def get_account_summaries():
    """List of per-account summaries (balances + parsed positions)."""
    data = get_accounts(include_positions=True)
    if not data:
        return []
    if isinstance(data, dict):
        data = [data]
    return [_summarize_account(a) for a in data]


# --------------------------------------------------------------------------- #
# Orders (working + filled) and transactions (fills/assignments)
# --------------------------------------------------------------------------- #
def _iso_z(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def get_orders(account_hash, days=14, status=None):
    """Orders for one account over a lookback window."""
    now = datetime.now(timezone.utc)
    params = {
        "fromEnteredTime": _iso_z(now - timedelta(days=days)),
        "toEnteredTime": _iso_z(now),
        "maxResults": 200,
    }
    if status:
        params["status"] = status  # e.g. WORKING, FILLED, CANCELED
    return _trader_get(f"accounts/{account_hash}/orders", params)


def get_transactions(account_hash, days=30, types="TRADE"):
    """Transactions (fills, assignments, etc.) for one account."""
    now = datetime.now(timezone.utc)
    params = {
        "startDate": _iso_z(now - timedelta(days=days)),
        "endDate": _iso_z(now),
    }
    if types:
        params["types"] = types
    return _trader_get(f"accounts/{account_hash}/transactions", params)


def _flatten_order(o):
    """Reduce a Schwab order object to the fields Aristotle needs."""
    legs = []
    for leg in o.get("orderLegCollection", []):
        instr = leg.get("instrument", {})
        legs.append({
            "instruction": leg.get("instruction"),      # BUY_TO_CLOSE, SELL_TO_OPEN...
            "symbol": instr.get("symbol"),
            "putCall": instr.get("putCall"),
            "assetType": instr.get("assetType"),
            "quantity": leg.get("quantity"),
        })
    return {
        "orderId": o.get("orderId"),
        "status": o.get("status"),                       # WORKING / FILLED / ...
        "orderType": o.get("orderType"),
        "price": o.get("price"),
        "duration": o.get("duration"),                   # GOOD_TILL_CANCEL / DAY
        "enteredTime": o.get("enteredTime"),
        "filledQuantity": o.get("filledQuantity"),
        "legs": legs,
    }


def get_working_orders(account_hash):
    """Only orders that are still live (WORKING/PENDING/QUEUED)."""
    orders = get_orders(account_hash, days=60) or []
    live_states = {"WORKING", "PENDING_ACTIVATION", "QUEUED", "ACCEPTED",
                   "AWAITING_CONDITION", "OPEN"}
    return [_flatten_order(o) for o in orders
            if str(o.get("status", "")).upper() in live_states]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_json(obj):
    print(json.dumps(obj, indent=2, default=str))


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Schwab Trader API (read-only)")
    ap.add_argument("--numbers", action="store_true", help="account# -> hash map")
    ap.add_argument("--accounts", action="store_true", help="balances + positions")
    ap.add_argument("--positions", action="store_true", help="flattened positions")
    ap.add_argument("--orders", action="store_true", help="orders")
    ap.add_argument("--transactions", action="store_true", help="transactions")
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args()

    if args.numbers:
        nums = get_account_numbers()
        for n in nums:
            print(f"  *{n['mask']}  {n['type']:<26}  hash={n['hashValue']}")
        if not nums:
            print("  (no accounts returned - check auth + app scope)")

    elif args.accounts or args.positions:
        summaries = get_account_summaries()
        for s in summaries:
            print(f"\n=== *{s['mask']} ({s['type']}) ===")
            print(f"  Net Liq:      ${s['net_liq']:,.2f}" if s['net_liq'] else "  Net Liq: N/A")
            print(f"  Cash:         ${s['cash']:,.2f}" if s['cash'] else "  Cash: N/A")
            print(f"  Open positions: {len(s['positions'])}")
            for p in s["positions"]:
                tag = p["putCall"] or p["assetType"]
                print(f"    {p['symbol']:<22} {tag:<8} qty={p['quantity']:<5} "
                      f"avg={p['average_price']} mv={p['market_value']}")

    elif args.orders:
        for n in get_account_numbers():
            print(f"\n=== Orders *{n['mask']} (last {args.days}d) ===")
            orders = get_orders(n["hashValue"], days=args.days) or []
            for o in orders:
                fo = _flatten_order(o)
                legs = "; ".join(f"{l['instruction']} {l['quantity']}x {l['symbol']}"
                                 for l in fo["legs"])
                print(f"  [{fo['status']:<10}] {fo['orderType']:<8} @ {fo['price']} "
                      f"({fo['duration']}) - {legs}")

    elif args.transactions:
        for n in get_account_numbers():
            print(f"\n=== Transactions *{n['mask']} (last {args.days}d) ===")
            _print_json(get_transactions(n["hashValue"], days=args.days))

    else:
        ap.print_help()
