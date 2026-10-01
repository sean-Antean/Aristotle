"""
execute.py - Aristotle GATED LIVE EXECUTION (separate entity from the advisory)
================================================================================
This is the ONLY module that can place an order. It is deliberately decoupled
from the read-only advisory (schwab_accounts.py / reconcile.py / flash_check.py
stay read-only). YOU make every decision (Guac + your ChatGPT project + Aristotle);
this only removes the manual setup friction once you've decided.

WHAT IT DOES
  - Builds the exact Schwab order for a cash-secured put as a ONE-TRIGGERS-OTHER
    (OTO) order: SELL_TO_OPEN the put, and on fill AUTO-PLACE the 50% BUY_TO_CLOSE
    GTC. One approval, and the harvest order sets itself. No forgotten GTC.
  - Auto-resolves the right IRA (*159 / *472) so you can't fat-finger the account.
  - Re-validates against your gameplan gates + caps against LIVE data.
  - DRY-RUN by default: shows the exact order JSON + ticket + a confirm token,
    and places NOTHING.

TRIPLE SAFETY GATE for a live submit (all required):
  1. gameplan.execution.enabled_live == true      (master switch, default false)
  2. --live AND --confirm <TOKEN> matching the exact order
  3. re-validation passes at submit time (gates/caps/OTM), + max-contracts cap

ADVISORY-ONLY SPIRIT PRESERVED: a human triggers every order. Aristotle never
submits autonomously, and never a bulk approval.

Usage:
  python execute.py csp --account 159 --ticker SOXL --strike 90 \
        --expiry 2026-09-18 --contracts 1 --limit 4.50           # DRY-RUN
  python execute.py csp ... --live --confirm A1B2C3                # LIVE (you run this)
"""
import argparse
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import schwab_bridge as mkt
import schwab_accounts as acct
import reconcile as rec
import flash_check as fc
from schwab_bridge import get_access_token, BASE_URL, get_ssl_context

TRADER_API_URL = f"{BASE_URL}/trader/v1"
CONFIG_DIR = Path(__file__).parent


def load_gp():
    return json.loads((CONFIG_DIR / "gameplan.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Live-authorization PIN (human-held; stored key-stretched, NOT in plaintext)
# --------------------------------------------------------------------------- #
AUTH_FILE = CONFIG_DIR / "execution_auth.json"
_PBKDF2_ITERS = 200_000


def _hash_pin(pin, salt_hex, iters=_PBKDF2_ITERS):
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt_hex), iters).hex()


def set_pin():
    """One-time: set the live-authorization PIN. Run this yourself at the desk."""
    p1 = getpass.getpass("Set a live-execution PIN (input hidden): ").strip()
    if len(p1) < 6:
        print("[abort] Use at least 6 characters (a short passphrase is better than 4 digits).")
        return
    p2 = getpass.getpass("Confirm PIN: ").strip()
    if p1 != p2:
        print("[abort] PINs did not match.")
        return
    salt = secrets.token_hex(16)
    AUTH_FILE.write_text(json.dumps({
        "salt": salt, "hash": _hash_pin(p1, salt), "iters": _PBKDF2_ITERS,
        "created_at": datetime.now().isoformat(),
    }, indent=2))
    try:
        os.chmod(AUTH_FILE, 0o600)
    except Exception:
        pass
    print(f"[OK] PIN set and stored (key-stretched) in {AUTH_FILE.name}. Keep it secret; "
          "it authorizes live orders.")


def verify_pin(pin):
    if not pin or not AUTH_FILE.exists():
        return False
    a = json.loads(AUTH_FILE.read_text())
    calc = _hash_pin(pin, a["salt"], a.get("iters", _PBKDF2_ITERS))
    return hmac.compare_digest(calc, a.get("hash", ""))


# --------------------------------------------------------------------------- #
# Kill-switch (disarm) + status — the ONLY safe-direction toggle
# --------------------------------------------------------------------------- #
GAMEPLAN_FILE = CONFIG_DIR / "gameplan.json"


def disarm():
    """Phone/desk kill-switch: force gameplan.execution.enabled_live -> false.
    This can ONLY turn live OFF, never on (arming stays a deliberate manual edit).
    Safe to run anytime, by anyone, including Aristotle on a 'stop trading' message.
    Surgical text edit so the hand-formatted gameplan.json is otherwise untouched."""
    text = GAMEPLAN_FILE.read_text(encoding="utf-8")
    new, n = re.subn(r'("enabled_live"\s*:\s*)true\b', r'\1false', text)
    if n == 0:
        cur = load_gp().get("execution", {}).get("enabled_live")
        print(f"[disarm] Already OFF (enabled_live={cur}). Live execution is not armed.")
        return
    GAMEPLAN_FILE.write_text(new, encoding="utf-8")
    after = load_gp().get("execution", {}).get("enabled_live")
    if after is False:
        print("[DISARMED] Live execution is now OFF (enabled_live -> false). No orders can be placed.")
    else:
        print(f"[!!] Wrote disarm but enabled_live is still {after} — check gameplan.json MANUALLY now.")


def status():
    """Read-only: show whether live execution is armed. Safe to run anytime."""
    ex = load_gp().get("execution", {})
    live = ex.get("enabled_live", False)
    print("=" * 48)
    print("ARISTOTLE EXECUTION STATUS")
    print("=" * 48)
    print(f"  LIVE EXECUTION : {'ARMED (ON)  <-- can place real orders' if live else 'OFF (safe) — no orders can be placed'}")
    print(f"  Live PIN set   : {'yes' if AUTH_FILE.exists() else 'NO (set via: python execute.py set-pin)'}")
    print(f"  Max contracts  : {ex.get('max_contracts_per_order', 5)} per order")
    print(f"  Auto 50% BTC   : {ex.get('auto_btc_50_gtc', True)}")
    print(f"  PIN required   : {ex.get('require_pin_for_live', True)}")
    if live:
        print("  To DISARM now: python execute.py disarm   (or tell Aristotle 'stop trading')")
    print("=" * 48)


# --------------------------------------------------------------------------- #
# Order construction
# --------------------------------------------------------------------------- #
def osi_symbol(underlying, expiry, right, strike):
    """OSI option symbol, e.g. SOXL 2026-09-18 90 Put -> 'SOXL  260918P00090000'."""
    yymmdd = datetime.strptime(expiry, "%Y-%m-%d").strftime("%y%m%d")
    cp = "P" if right.upper().startswith("P") else "C"
    strike_int = int(round(float(strike) * 1000))
    return f"{underlying.upper().ljust(6)}{yymmdd}{cp}{strike_int:08d}"


def build_csp_order(underlying, expiry, strike, contracts, limit, auto_btc_50=True):
    """CSP as an OTO order: SELL_TO_OPEN put (LIMIT/DAY), child BUY_TO_CLOSE @ 50% GTC."""
    sym = osi_symbol(underlying, expiry, "P", strike)
    entry_leg = [{
        "instruction": "SELL_TO_OPEN",
        "quantity": contracts,
        "instrument": {"symbol": sym, "assetType": "OPTION"},
    }]
    order = {
        "orderType": "LIMIT",
        "session": "NORMAL",
        "price": f"{float(limit):.2f}",
        "duration": "DAY",
        "orderStrategyType": "SINGLE",
        "orderLegCollection": entry_leg,
    }
    if auto_btc_50:
        btc_price = round(float(limit) * 0.5, 2)
        order["orderStrategyType"] = "TRIGGER"
        order["childOrderStrategies"] = [{
            "orderType": "LIMIT",
            "session": "NORMAL",
            "price": f"{btc_price:.2f}",
            "duration": "GOOD_TILL_CANCEL",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [{
                "instruction": "BUY_TO_CLOSE",
                "quantity": contracts,
                "instrument": {"symbol": sym, "assetType": "OPTION"},
            }],
        }]
    return order, sym


def confirm_token(account, ticker, expiry, strike, contracts, limit, right="P"):
    """Deterministic 6-char token bound to the EXACT order, so a live --confirm
    can only fire the order it was shown for (no fat-fingering a different one).
    `right` binds the token to a PUT vs CALL, so a CSP token can't fire a call."""
    r = "C" if str(right).upper().startswith("C") else "P"
    canon = f"{account}|{ticker.upper()}|{expiry}|{r}|{float(strike):g}|{contracts}|{float(limit):.2f}"
    return hashlib.sha1(canon.encode()).hexdigest()[:6].upper()


# --------------------------------------------------------------------------- #
# Re-validation against LIVE data (gates + caps) — same rules as the advisory
# --------------------------------------------------------------------------- #
def validate(account, ticker, strike, contracts, limit, gp, snap=None):
    ticker = ticker.upper()
    checks = []
    ok = True

    def add(label, passed, detail=""):
        nonlocal ok
        checks.append((label, passed, detail))
        if not passed:
            ok = False

    # Universe
    core = set(gp["watchlists"]["core"]); flex = set(gp["watchlists"]["flex"])
    add("On Core/Flex watchlist", ticker in core or ticker in flex,
        "not on watchlist" if ticker not in core | flex else ticker)

    # Market + trend gates
    qqq = fc.cloud_score("QQQ", "daily")
    d = fc.cloud_score(ticker, "daily")
    w = fc.cloud_score(ticker, "weekly")
    add("QQQ market gate >=2/3", (qqq.get("score") or 0) >= 2, f"QQQ {qqq.get('score')}/3")
    add("Weekly trend >=2/3 (senior)", (w.get("score") or 0) >= 2, f"weekly {w.get('score')}/3")
    add("Daily trend >=2/3", (d.get("score") or 0) >= 2, f"daily {d.get('score')}/3")

    # OTM put (strike below current price)
    q = (mkt.get_quotes([ticker]) or {}).get(ticker) or {}
    px = q.get("price")
    add("OTM put (strike < price)", px is not None and float(strike) < px,
        f"px ${px} / strike {strike}")

    # Sizing / caps
    snap = snap or rec.build_snapshot()
    collateral = float(strike) * 100 * contracts
    head = fc.sizing_headroom(ticker, snap, gp)
    add("Within sizing caps", collateral <= head["max_collateral"] + 1,
        f"order ${collateral:,.0f} vs room ${head['max_collateral']:,.0f}")

    # Chosen account has per-IRA room
    a = next((x for x in snap["accounts"] if str(x["mask"]) == str(account)), None)
    if a:
        ira_cap = gp["position_rules"]["max_single_ira_concentration_pct"] * (a["net_liq"] or 0)
        room = ira_cap - a["committed_collateral"]
        add(f"IRA *{account} concentration room", collateral <= room + 1,
            f"order ${collateral:,.0f} vs room ${room:,.0f}")
    else:
        add(f"Account *{account} exists", False, "account not found in snapshot")

    # Max contracts
    cap = gp.get("execution", {}).get("max_contracts_per_order", 5)
    add(f"Contracts <= {cap}/order", contracts <= cap, f"{contracts} contracts")

    return ok, checks, head, px


# --------------------------------------------------------------------------- #
# Live submit (POST) — guarded; a human triggers this
# --------------------------------------------------------------------------- #
def _trader_post_order(account_hash, order):
    token = get_access_token()
    req = urllib.request.Request(
        f"{TRADER_API_URL}/accounts/{account_hash}/orders",
        data=json.dumps(order).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, context=get_ssl_context()) as resp:
            loc = resp.headers.get("Location", "")
            oid = loc.rstrip("/").split("/")[-1] if loc else "(no id returned)"
            return resp.status, oid, None
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode(errors="replace")[:400]
        except Exception:
            pass
        return e.code, None, body
    except Exception as e:
        return None, None, str(e)


# --------------------------------------------------------------------------- #
# CSP command (dry-run default; live requires the triple gate)
# --------------------------------------------------------------------------- #
def cmd_csp(args):
    gp = load_gp()
    ex = gp.get("execution", {})
    ticker = args.ticker.upper()
    tok = confirm_token(args.account, ticker, args.expiry, args.strike, args.contracts, args.limit)

    snap = rec.build_snapshot()
    ok, checks, head, px = validate(args.account, ticker, args.strike, args.contracts,
                                    args.limit, gp, snap)
    order, sym = build_csp_order(ticker, args.expiry, args.strike, args.contracts,
                                 args.limit, ex.get("auto_btc_50_gtc", True))
    collateral = float(args.strike) * 100 * args.contracts
    credit = float(args.limit) * 100 * args.contracts

    mode = "SIMULATE (dress rehearsal)" if args.simulate else ("LIVE ORDER" if args.live else "DRY-RUN")
    print("=" * 64)
    print(f"{mode}  |  CSP  {ticker} {args.strike:g}P x{args.contracts}  IRA *{args.account}")
    print("=" * 64)
    print(f"  SELL TO OPEN {args.contracts}x {ticker} {args.strike:g} PUT {args.expiry}")
    print(f"  LIMIT ${float(args.limit):.2f} DAY   ->  credit ~${credit:,.0f} | collateral ${collateral:,.0f}")
    if ex.get("auto_btc_50_gtc", True):
        print(f"  + AUTO on fill: BUY TO CLOSE GTC @ ${round(float(args.limit)*0.5,2):.2f} (50%)")
    print(f"  OSI symbol: {sym}")
    print("-" * 64)
    print("  VALIDATION (live gates + caps):")
    for label, passed, detail in checks:
        print(f"    [{'OK' if passed else 'XX'}] {label:<32} {detail}")
    print("-" * 64)

    if args.simulate:
        # Full live pipeline, reported gate-by-gate, but NOTHING is sent.
        nums = {str(n["mask"]): n["hashValue"] for n in (acct.get_account_numbers() or [])}
        ahash = nums.get(str(args.account))
        cap = ex.get("max_contracts_per_order", 5)
        live_on = ex.get("enabled_live", False)
        print("  SIMULATION — runs the entire live gate sequence, sends nothing:")
        print(f"    [{'OK' if live_on else '--'}] master switch enabled_live = {live_on}"
              + ("" if live_on else "   <- LIVE would REFUSE here until you flip it"))
        print(f"    [OK] confirm token for THIS exact order = {tok}   (live needs --confirm {tok})")
        if ex.get("require_pin_for_live", False):
            pin_set = AUTH_FILE.exists()
            print(f"    [{'OK' if pin_set else '--'}] live PIN gate ON — "
                  + ("PIN set; live needs your PIN" if pin_set
                     else "no PIN set yet (run: python execute.py set-pin)"))
        print(f"    [{'OK' if ok else 'XX'}] submit-time re-validation {'passed' if ok else 'FAILED'}")
        print(f"    [{'OK' if ahash else 'XX'}] account *{args.account} resolved -> "
              + (f"hash ...{ahash[-6:]}" if ahash else "NOT FOUND"))
        print(f"    [{'OK' if args.contracts <= cap else 'XX'}] contracts {args.contracts} <= {cap}/order")
        print("-" * 64)
        print(f"  [SIMULATE] Would POST to /trader/v1/accounts/{('...'+ahash[-6:]) if ahash else '???'}/orders:")
        print(json.dumps(order, indent=2))
        print("  Nothing was sent — this rehearsal never reaches Schwab.")
        print("=" * 64)
        return

    if not args.live:
        print("  DRY-RUN — nothing was placed.")
        print(f"  Exact order JSON:\n{json.dumps(order, indent=2)}")
        print("-" * 64)
        if ok:
            base = (f"python execute.py csp --account {args.account} --ticker {ticker} "
                    f"--strike {args.strike:g} --expiry {args.expiry} --contracts {args.contracts} "
                    f"--limit {float(args.limit):.2f} --live --confirm {tok}")
            print(f"  To place it LIVE at the DESK (you'll be prompted for your PIN):")
            print(f"    {base}")
            if ex.get("require_pin_for_live", False):
                print(f"  PHONE form (Aristotle appends your PIN once you reply it):")
                print(f"    {base} --pin <YOUR_PIN>")
            if not ex.get("enabled_live", False):
                print("  NOTE: live is OFF (gameplan.execution.enabled_live=false). Flip it to true to arm.")
            if ex.get("require_pin_for_live", False) and not AUTH_FILE.exists():
                print("  NOTE: no PIN set yet. Run once at the desk: python execute.py set-pin")
        else:
            print("  Validation FAILED — fix the flagged items; live submit is blocked.")
        print("=" * 64)
        return

    # ---- LIVE PATH: triple gate ----
    if not ex.get("enabled_live", False):
        print("  REFUSED: gameplan.execution.enabled_live is false (master switch off).")
        print("=" * 64); return
    if ex.get("require_confirm_token", True) and (args.confirm or "").upper() != tok:
        print(f"  REFUSED: confirm token mismatch. Expected {tok} for THIS exact order.")
        print("=" * 64); return
    if not ok:
        print("  REFUSED: live re-validation failed (see flags above).")
        print("=" * 64); return
    cap = ex.get("max_contracts_per_order", 5)
    if args.contracts > cap:
        print(f"  REFUSED: {args.contracts} contracts exceeds max_contracts_per_order ({cap}).")
        print("=" * 64); return
    if ex.get("require_pin_for_live", False):
        if not AUTH_FILE.exists():
            print("  REFUSED: live PIN required but none set. Run once: python execute.py set-pin")
            print("=" * 64); return
        pin = args.pin
        if not pin and sys.stdin.isatty():          # desk: prompt (keeps it out of shell history)
            pin = getpass.getpass("  Live PIN: ").strip()
        if not verify_pin(pin):
            print("  REFUSED: live PIN missing or incorrect (your per-order authorization).")
            print("=" * 64); return

    nums = {str(n["mask"]): n["hashValue"] for n in (acct.get_account_numbers() or [])}
    ahash = nums.get(str(args.account))
    if not ahash:
        print(f"  REFUSED: could not resolve account *{args.account}.")
        print("=" * 64); return

    print("  All gates passed -> submitting LIMIT order...")
    status, oid, err = _trader_post_order(ahash, order)
    if err:
        print(f"  SUBMIT FAILED (HTTP {status}): {err}")
    else:
        print(f"  SUBMITTED. status {status}, order id {oid}")
        print("  Verify in Schwab. The 50% BTC GTC arms automatically on fill.")
    print("=" * 64)


# --------------------------------------------------------------------------- #
# BTC command: buy-to-close an OPEN short put at 50% (GTC) — position management
# --------------------------------------------------------------------------- #
def find_short_puts(snap, account, ticker, strike=None, expiry=None):
    out = []
    for p in snap.get("open_options", []):
        if str(p.get("account_mask")) != str(account):
            continue
        if p.get("underlying") != ticker.upper() or p.get("type") != "PUT":
            continue
        if strike is not None and abs((p.get("strike") or 0) - strike) > 0.001:
            continue
        if expiry is not None and p.get("expiry") != expiry:
            continue
        out.append(p)
    return out


def build_btc_order(symbol, contracts, price):
    return {
        "orderType": "LIMIT", "session": "NORMAL", "price": f"{price:.2f}",
        "duration": "GOOD_TILL_CANCEL", "orderStrategyType": "SINGLE",
        "orderLegCollection": [{
            "instruction": "BUY_TO_CLOSE", "quantity": contracts,
            "instrument": {"symbol": symbol, "assetType": "OPTION"},
        }],
    }


def build_cc_order(underlying, expiry, strike, contracts, limit, duration="DAY", auto_btc_50=True):
    """Covered call: SELL_TO_OPEN a call (LIMIT). Per gameplan.covered_calls.post_fill_exit
    ('50% GTC Buy to Close immediately after fill'), attach an OTO child that auto-places
    the 50% BUY_TO_CLOSE GTC on fill — same churn discipline as the CSP. auto_btc_50=False
    (--no-btc) skips it for the 'trend_expansion / let it run to the strike' case.
    duration DAY (fill today) or GTC (rest until filled)."""
    sym = osi_symbol(underlying, expiry, "C", strike)
    dur = "GOOD_TILL_CANCEL" if str(duration).upper().startswith("G") else "DAY"
    order = {
        "orderType": "LIMIT", "session": "NORMAL", "price": f"{float(limit):.2f}",
        "duration": dur, "orderStrategyType": "SINGLE",
        "orderLegCollection": [{
            "instruction": "SELL_TO_OPEN", "quantity": contracts,
            "instrument": {"symbol": sym, "assetType": "OPTION"},
        }],
    }
    if auto_btc_50:
        btc_price = round(float(limit) * 0.5, 2)
        order["orderStrategyType"] = "TRIGGER"
        order["childOrderStrategies"] = [{
            "orderType": "LIMIT", "session": "NORMAL", "price": f"{btc_price:.2f}",
            "duration": "GOOD_TILL_CANCEL", "orderStrategyType": "SINGLE",
            "orderLegCollection": [{
                "instruction": "BUY_TO_CLOSE", "quantity": contracts,
                "instrument": {"symbol": sym, "assetType": "OPTION"},
            }],
        }]
    return order, sym


_LIVE_STATES = {"WORKING", "PENDING_ACTIVATION", "QUEUED", "ACCEPTED",
                "AWAITING_CONDITION", "OPEN"}


def existing_btc_covers(account_hash, symbol):
    """True if a LIVE BUY_TO_CLOSE for this exact option already exists — INCLUDING
    OTO child orders (an auto-50%-BTC attached to a filled csp entry). Scanning the
    nested childOrderStrategies is essential: without it this guard would miss an
    OTO hedge and let a duplicate close-order through (over-hedge risk)."""
    found = []

    def scan(o):
        if str(o.get("status", "")).upper() in _LIVE_STATES:
            for leg in o.get("orderLegCollection", []) or []:
                if (leg.get("instruction") == "BUY_TO_CLOSE"
                        and (leg.get("instrument") or {}).get("symbol") == symbol):
                    found.append(True)
        for c in o.get("childOrderStrategies", []) or []:
            scan(c)

    try:
        for o in acct.get_orders(account_hash, days=5) or []:
            scan(o)
    except Exception:
        pass
    return bool(found)


def cmd_btc(args):
    gp = load_gp()
    ex = gp.get("execution", {})
    ticker = args.ticker.upper()
    snap = rec.build_snapshot()
    matches = find_short_puts(snap, args.account, ticker, args.strike, args.expiry)

    mode = "SIMULATE (dress rehearsal)" if args.simulate else ("LIVE ORDER" if args.live else "DRY-RUN")
    print("=" * 64)
    print(f"{mode}  |  BTC 50%  {ticker}  IRA *{args.account}")
    print("=" * 64)
    if not matches:
        print(f"  REFUSED: no open short {ticker} PUT in *{args.account}. Nothing to close.")
        print("=" * 64); return
    if len(matches) > 1:
        print(f"  Multiple {ticker} short puts — add --strike and/or --expiry:")
        for p in matches:
            print(f"    {p['strike']:g}P {p['expiry']} x{int(p['contracts'])}")
        print("=" * 64); return

    pos = matches[0]
    strike, expiry, contracts = pos["strike"], pos["expiry"], int(pos["contracts"])
    entry = pos.get("entry_premium")
    pct = gp.get("exit_rules", {}).get("profit_gtc_pct", 0.50)
    if not entry:
        print("  REFUSED: no entry premium on the position — can't compute the 50% level.")
        print("=" * 64); return
    btc_price = round(float(args.limit), 2) if getattr(args, "limit", None) else round(entry * pct, 2)
    sym = osi_symbol(ticker, expiry, "P", strike)
    order = build_btc_order(sym, contracts, btc_price)
    tok = confirm_token(args.account, ticker, expiry, strike, contracts, btc_price)
    prof_pct = (1 - btc_price / entry) * 100 if entry else 0

    print(f"  Position: SHORT {contracts}x {ticker} {strike:g}P {expiry}  (entry ${entry:.4f})")
    print(f"  Order:    BUY TO CLOSE {contracts}x {ticker} {strike:g}P {expiry}")
    print(f"            LIMIT ${btc_price:.2f} GTC  (take {prof_pct:.0f}pct profit; buyback {btc_price/entry*100:.0f}pct of ${entry:.2f}) -> ~${btc_price*100*contracts:,.0f} to close")
    print(f"  OSI symbol: {sym}")
    print("-" * 64)

    nums = {str(n["mask"]): n["hashValue"] for n in (acct.get_account_numbers() or [])}
    ahash = nums.get(str(args.account))
    dup = existing_btc_covers(ahash, sym) if ahash else False
    price_ok = 0 < btc_price < entry
    checks_ok = (not dup) and price_ok
    print("  SAFETY:")
    print(f"    [OK] position exists (SHORT {contracts}x {ticker} {strike:g}P)")
    print(f"    [{'XX -> REFUSING' if dup else 'OK'}] no duplicate 50% GTC already working")
    print(f"    [{'OK' if price_ok else 'XX'}] BTC price sane (0 < ${btc_price:.2f} < entry ${entry:.2f})")
    print("-" * 64)

    if args.simulate:
        live_on = ex.get("enabled_live", False)
        print("  SIMULATION — full live pipeline, sends nothing:")
        print(f"    [{'OK' if live_on else '--'}] enabled_live = {live_on}"
              + ("" if live_on else "  <- LIVE would REFUSE"))
        print(f"    [OK] confirm token = {tok}")
        if ex.get("require_pin_for_live", False):
            print(f"    [{'OK' if AUTH_FILE.exists() else '--'}] live PIN {'set' if AUTH_FILE.exists() else 'NOT set'}")
        print(f"    [{'OK' if checks_ok else 'XX'}] safety checks {'passed' if checks_ok else 'FAILED'}")
        print(f"    [{'OK' if ahash else 'XX'}] account resolved -> {'...'+ahash[-6:] if ahash else 'NOT FOUND'}")
        print(f"  [SIMULATE] Would POST to /accounts/{('...'+ahash[-6:]) if ahash else '???'}/orders:")
        print(json.dumps(order, indent=2))
        print("  Nothing was sent."); print("=" * 64); return

    if not args.live:
        print("  DRY-RUN — nothing placed.")
        if checks_ok:
            lim = f" --limit {btc_price}" if getattr(args, "limit", None) else ""
            base = (f"python execute.py btc --account {args.account} --ticker {ticker} "
                    f"--strike {strike:g} --expiry {expiry}{lim} --live --confirm {tok}")
            print("  To place LIVE at the desk (prompts for PIN):")
            print(f"    {base}")
            if ex.get("require_pin_for_live", False):
                print(f"  PHONE form (Aristotle appends your PIN): {base} --pin <YOUR_PIN>")
            if not ex.get("enabled_live", False):
                print("  NOTE: live is OFF (enabled_live=false). Arm it first.")
        else:
            print("  Safety checks FAILED — live is blocked.")
        print("=" * 64); return

    # ---- LIVE ----
    if not ex.get("enabled_live", False):
        print("  REFUSED: enabled_live is false (master switch off)."); print("=" * 64); return
    if ex.get("require_confirm_token", True) and (args.confirm or "").upper() != tok:
        print(f"  REFUSED: confirm token mismatch (expected {tok})."); print("=" * 64); return
    if not checks_ok:
        print("  REFUSED: safety checks failed (see above)."); print("=" * 64); return
    if ex.get("require_pin_for_live", False):
        if not AUTH_FILE.exists():
            print("  REFUSED: live PIN required but not set (python execute.py set-pin)."); print("=" * 64); return
        pin = args.pin
        if not pin and sys.stdin.isatty():
            pin = getpass.getpass("  Live PIN: ").strip()
        if not verify_pin(pin):
            print("  REFUSED: live PIN missing or incorrect."); print("=" * 64); return
    if not ahash:
        print(f"  REFUSED: could not resolve account *{args.account}."); print("=" * 64); return
    print("  All gates passed -> submitting BUY_TO_CLOSE GTC...")
    status, oid, err = _trader_post_order(ahash, order)
    if err:
        print(f"  SUBMIT FAILED (HTTP {status}): {err}")
    else:
        print(f"  SUBMITTED. status {status}, order id {oid}")
        print(f"  {ticker} {strike:g}P is now covered by a 50% GTC buy-to-close.")
    print("=" * 64)


# --------------------------------------------------------------------------- #
# CC command: sell a covered call against shares you OWN (wheel: post-assignment)
# --------------------------------------------------------------------------- #
def find_shares(account, ticker):
    """Return (long_shares, avg_price) for the equity/ETF `ticker` in IRA *account
    from LIVE account data. (0, None) if not held. Used to PROVE a call is covered."""
    ticker = ticker.upper()
    try:
        accts = acct.get_accounts()
    except Exception:
        return 0, None
    if isinstance(accts, dict):
        accts = [accts]
    for a in accts or []:
        sec = a.get("securitiesAccount", a)
        if str(sec.get("accountNumber", ""))[-3:] != str(account):
            continue
        for p in sec.get("positions", []) or []:
            instr = p.get("instrument", {}) or {}
            if instr.get("symbol", "").upper() != ticker:
                continue
            if instr.get("assetType") not in ("EQUITY", "COLLECTIVE_INVESTMENT", "ETF"):
                continue
            qty = (p.get("longQuantity", 0) or 0) - (p.get("shortQuantity", 0) or 0)
            return int(qty), p.get("averagePrice")
    return 0, None


def existing_short_calls(account, ticker):
    """Contracts of OPEN short CALLs on `ticker` in *account — shares already committed
    to a cover, so they must be subtracted before selling ANOTHER call (else partial naked)."""
    ticker = ticker.upper()
    total = 0
    try:
        accts = acct.get_accounts()
    except Exception:
        return 0
    if isinstance(accts, dict):
        accts = [accts]
    for a in accts or []:
        sec = a.get("securitiesAccount", a)
        if str(sec.get("accountNumber", ""))[-3:] != str(account):
            continue
        for p in sec.get("positions", []) or []:
            instr = p.get("instrument", {}) or {}
            if instr.get("assetType") != "OPTION":
                continue
            info = rec.parse_option_symbol(instr.get("symbol", ""))
            if info and info["underlying"] == ticker and info["type"] == "CALL":
                total += int(p.get("shortQuantity", 0) or 0)
    return total


def validate_cc(account, ticker, strike, contracts, gp, shares, basis, committed_calls=0):
    """Covered-call gates. The HARD gate is COVERED (UNCOMMITTED shares >= contracts x100)
    so this can NEVER place a naked call — even a second call against already-covered shares.
    Strike materially below basis is a hard block per gameplan.covered_calls.basis_protection
    (unless you deliberately pass a lower --basis to exit at a loss)."""
    checks = []
    ok = True

    def add(label, passed, detail="", hard=True):
        nonlocal ok
        checks.append((label, passed, detail, hard))
        if hard and not passed:
            ok = False

    need = contracts * 100
    avail = shares - committed_calls * 100
    add("COVERED (uncommitted shares >= contracts x100)", avail >= need,
        f"own {shares} sh, {committed_calls} call(s) already sold, {avail} free, need {need}")
    cap = gp.get("execution", {}).get("max_contracts_per_order", 5)
    add(f"Contracts <= {cap}/order", contracts <= cap, f"{contracts} contracts")
    add("Strike sane (> 0)", float(strike) > 0, f"strike {strike:g}")
    if basis is not None:
        # basis_protection: block selling >2% below basis (locks a loss if called)
        floor = float(basis) * 0.98
        add("Strike not materially below basis", float(strike) >= floor,
            f"strike {strike:g} vs basis ${float(basis):.2f} (floor ${floor:.2f})")
    return ok, checks, cap


def cmd_cc(args):
    gp = load_gp()
    ex = gp.get("execution", {})
    ticker = args.ticker.upper()
    shares, avg = find_shares(args.account, ticker)
    basis = args.basis if args.basis is not None else avg
    q = (mkt.get_quotes([ticker]) or {}).get(ticker) or {}
    px = q.get("price")
    tok = confirm_token(args.account, ticker, args.expiry, args.strike,
                        args.contracts, args.limit, right="C")
    committed = existing_short_calls(args.account, ticker)
    ok, checks, cap = validate_cc(args.account, ticker, args.strike, args.contracts,
                                  gp, shares, basis, committed)
    auto_btc = ex.get("auto_btc_50_gtc", True) and not args.no_btc
    order, sym = build_cc_order(ticker, args.expiry, args.strike, args.contracts,
                                args.limit, args.duration, auto_btc)
    credit = float(args.limit) * 100 * args.contracts
    dur = "GTC" if str(args.duration).upper().startswith("G") else "DAY"

    mode = "SIMULATE (dress rehearsal)" if args.simulate else ("LIVE ORDER" if args.live else "DRY-RUN")
    print("=" * 64)
    print(f"{mode}  |  COVERED CALL  {ticker} {args.strike:g}C x{args.contracts}  IRA *{args.account}")
    print("=" * 64)
    print(f"  SELL TO OPEN {args.contracts}x {ticker} {args.strike:g} CALL {args.expiry}")
    print(f"  LIMIT ${float(args.limit):.2f} {dur}   ->  credit ~${credit:,.0f}")
    if auto_btc:
        print(f"  + AUTO on fill: BUY TO CLOSE GTC @ ${round(float(args.limit)*0.5,2):.2f} (50% churn)")
    else:
        print(f"  (no auto-BTC: --no-btc set — let it run to the strike)")
    bstr = f"${float(basis):.2f}" if basis is not None else "n/a"
    print(f"  Shares held: {shares}  (basis {bstr})  |  spot ${px}")
    if basis is not None:
        called_gain = (float(args.strike) - float(basis)) * 100 * args.contracts + credit
        print(f"  If called away at {args.strike:g}: total gain ~${called_gain:,.0f}")
    print(f"  OSI symbol: {sym}")
    print("-" * 64)
    print("  VALIDATION:")
    for label, passed, detail, hard in checks:
        tag = "OK" if passed else ("XX" if hard else "!!")
        print(f"    [{tag}] {label:<36} {detail}")
    if not ok:
        print("    (XX = hard gate failed; !! = soft warning only)")
    print("-" * 64)

    if args.simulate:
        nums = {str(n["mask"]): n["hashValue"] for n in (acct.get_account_numbers() or [])}
        ahash = nums.get(str(args.account))
        live_on = ex.get("enabled_live", False)
        print("  SIMULATION — runs the entire live gate sequence, sends nothing:")
        print(f"    [{'OK' if live_on else '--'}] master switch enabled_live = {live_on}"
              + ("" if live_on else "   <- LIVE would REFUSE until you flip it"))
        print(f"    [OK] confirm token for THIS exact order = {tok}   (live needs --confirm {tok})")
        if ex.get("require_pin_for_live", False):
            print(f"    [{'OK' if AUTH_FILE.exists() else '--'}] live PIN "
                  + ("set" if AUTH_FILE.exists() else "NOT set (python execute.py set-pin)"))
        print(f"    [{'OK' if ok else 'XX'}] covered-call re-validation {'passed' if ok else 'FAILED'}")
        print(f"    [{'OK' if ahash else 'XX'}] account *{args.account} resolved -> "
              + (f"hash ...{ahash[-6:]}" if ahash else "NOT FOUND"))
        print(f"  [SIMULATE] Would POST to /trader/v1/accounts/{('...'+ahash[-6:]) if ahash else '???'}/orders:")
        print(json.dumps(order, indent=2))
        print("  Nothing was sent — this rehearsal never reaches Schwab.")
        print("=" * 64); return

    if not args.live:
        print("  DRY-RUN — nothing was placed.")
        print(f"  Exact order JSON:\n{json.dumps(order, indent=2)}")
        print("-" * 64)
        if ok:
            base = (f"python execute.py cc --account {args.account} --ticker {ticker} "
                    f"--strike {args.strike:g} --expiry {args.expiry} --contracts {args.contracts} "
                    f"--limit {float(args.limit):.2f} --duration {dur} --live --confirm {tok}")
            print("  To place it LIVE at the DESK (you'll be prompted for your PIN):")
            print(f"    {base}")
            if ex.get("require_pin_for_live", False):
                print(f"  PHONE form (Aristotle appends your PIN once you reply it):\n    {base} --pin <YOUR_PIN>")
            if not ex.get("enabled_live", False):
                print("  NOTE: live is OFF (enabled_live=false). Arm it first.")
        else:
            print("  Hard gate FAILED — live submit is blocked (see XX above).")
        print("=" * 64); return

    # ---- LIVE PATH: same triple gate as CSP ----
    if not ex.get("enabled_live", False):
        print("  REFUSED: enabled_live is false (master switch off)."); print("=" * 64); return
    if ex.get("require_confirm_token", True) and (args.confirm or "").upper() != tok:
        print(f"  REFUSED: confirm token mismatch. Expected {tok} for THIS exact order."); print("=" * 64); return
    if not ok:
        print("  REFUSED: covered-call re-validation failed (see XX flags above)."); print("=" * 64); return
    if args.contracts > cap:
        print(f"  REFUSED: {args.contracts} contracts exceeds max_contracts_per_order ({cap})."); print("=" * 64); return
    if ex.get("require_pin_for_live", False):
        if not AUTH_FILE.exists():
            print("  REFUSED: live PIN required but none set (python execute.py set-pin)."); print("=" * 64); return
        pin = args.pin
        if not pin and sys.stdin.isatty():
            pin = getpass.getpass("  Live PIN: ").strip()
        if not verify_pin(pin):
            print("  REFUSED: live PIN missing or incorrect."); print("=" * 64); return
    nums = {str(n["mask"]): n["hashValue"] for n in (acct.get_account_numbers() or [])}
    ahash = nums.get(str(args.account))
    if not ahash:
        print(f"  REFUSED: could not resolve account *{args.account}."); print("=" * 64); return
    print("  All gates passed -> submitting covered call...")
    status_code, oid, err = _trader_post_order(ahash, order)
    if err:
        print(f"  SUBMIT FAILED (HTTP {status_code}): {err}")
    else:
        print(f"  SUBMITTED. status {status_code}, order id {oid}")
        print(f"  {ticker} {args.strike:g}C is working. Verify in Schwab.")
    print("=" * 64)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Aristotle gated live execution")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("csp", help="cash-secured put (OTO with auto 50pct BTC)")
    c.add_argument("--account", required=True, help="IRA mask: 159 or 472")
    c.add_argument("--ticker", required=True)
    c.add_argument("--strike", type=float, required=True)
    c.add_argument("--expiry", required=True, help="YYYY-MM-DD")
    c.add_argument("--contracts", type=int, required=True)
    c.add_argument("--limit", type=float, required=True, help="credit limit per contract")
    c.add_argument("--live", action="store_true", help="actually place it (triple-gated)")
    c.add_argument("--simulate", action="store_true", help="dress rehearsal: full live pipeline, sends nothing")
    c.add_argument("--confirm", help="confirm token bound to the exact order")
    c.add_argument("--pin", help="live authorization PIN (desk: omit to be prompted; phone: agent appends it)")

    b = sub.add_parser("btc", help="buy-to-close an open short put at 50pct GTC (position mgmt)")
    b.add_argument("--account", required=True, help="IRA mask: 159 or 472")
    b.add_argument("--ticker", required=True)
    b.add_argument("--strike", type=float, help="only if multiple positions match")
    b.add_argument("--expiry", help="YYYY-MM-DD, only if multiple match")
    b.add_argument("--limit", type=float, help="custom buyback price (default: auto 50pct of entry)")
    b.add_argument("--live", action="store_true", help="actually place it (gated)")
    b.add_argument("--simulate", action="store_true", help="dress rehearsal: sends nothing")
    b.add_argument("--confirm", help="confirm token bound to the exact order")
    b.add_argument("--pin", help="live authorization PIN")

    cc = sub.add_parser("cc", help="covered call: sell a call against shares you own (post-assignment)")
    cc.add_argument("--account", required=True, help="IRA mask: 159 or 472")
    cc.add_argument("--ticker", required=True)
    cc.add_argument("--strike", type=float, required=True)
    cc.add_argument("--expiry", required=True, help="YYYY-MM-DD")
    cc.add_argument("--contracts", type=int, required=True)
    cc.add_argument("--limit", type=float, required=True, help="credit limit per contract")
    cc.add_argument("--basis", type=float, default=None,
                    help="your effective cost basis (defaults to Schwab avg price)")
    cc.add_argument("--duration", default="DAY", help="DAY (fill today) or GTC")
    cc.add_argument("--no-btc", action="store_true",
                    help="skip the auto 50pct BTC child (trend_expansion: let it run to the strike)")
    cc.add_argument("--live", action="store_true", help="actually place it (gated)")
    cc.add_argument("--simulate", action="store_true", help="dress rehearsal: sends nothing")
    cc.add_argument("--confirm", help="confirm token bound to the exact order")
    cc.add_argument("--pin", help="live authorization PIN")

    sub.add_parser("set-pin", help="set/replace the live-execution PIN (run once, at the desk)")
    sub.add_parser("disarm", help="KILL-SWITCH: force live execution OFF (safe anytime, phone-ok)")
    sub.add_parser("status", help="show whether live execution is armed (read-only)")
    # NOTE: there is deliberately NO 'arm' command. Arming enabled_live=true is a
    # manual, out-of-band human edit to gameplan.json — never an agent/Telegram action.
    args = ap.parse_args()
    if args.cmd == "set-pin":
        set_pin()
    elif args.cmd == "disarm":
        disarm()
    elif args.cmd == "status":
        status()
    elif args.cmd == "csp":
        if args.live and args.simulate:
            ap.error("choose one: --simulate (rehearsal) OR --live (real). Not both.")
        cmd_csp(args)
    elif args.cmd == "btc":
        if args.live and args.simulate:
            ap.error("choose one: --simulate (rehearsal) OR --live (real). Not both.")
        cmd_btc(args)
    elif args.cmd == "cc":
        if args.live and args.simulate:
            ap.error("choose one: --simulate (rehearsal) OR --live (real). Not both.")
        cmd_cc(args)
