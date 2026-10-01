"""
Aristotle v4.0 - Live Reconciliation Engine
===========================================
Answers the user's core problem: "I can't reconcile my trades in real time."

Pulls LIVE data from both Schwab IRAs (via schwab_accounts.py), loads the
Master Operating Plan rules (gameplan.json), and produces the Section-12
"Daily Execution Checker" snapshot plus hard-rule guardrail checks:

  A. Portfolio snapshot   (combined + per-IRA net liq, cash %, positions)
  C. Existing positions   (50% progress, DTE, GTC-coverage, trend flags)
  + Guardrail audit       (10% ticker / 25% IRA / 70% deploy / 30% cash / counts)
  + Missing-GTC detector  (every short option should have a 50% BTC working)

ADVISORY-ONLY. This module reads and reports. It never places orders.

Usage:
    python reconcile.py                 # full live reconciliation report
    python reconcile.py --json          # machine-readable output only
    python reconcile.py --save          # also write state/reconcile_*.json
"""

import json
import re
from datetime import datetime
from pathlib import Path

import schwab_accounts as sa

CONFIG_DIR = Path(__file__).parent
GAMEPLAN_FILE = CONFIG_DIR / "gameplan.json"
STATE_DIR = CONFIG_DIR / "state"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def load_gameplan():
    with open(GAMEPLAN_FILE, encoding="utf-8") as f:
        return json.load(f)


# Schwab OSI option symbol, e.g. "AMZU  260821P00040000"
_OPT_RE = re.compile(r"^(?P<root>[A-Z]+)\s+(?P<exp>\d{6})(?P<cp>[CP])(?P<strike>\d{8})$")


def parse_option_symbol(symbol):
    """Return {underlying, expiry(date), type, strike} or None for non-options."""
    if not symbol:
        return None
    m = _OPT_RE.match(symbol.strip())
    if not m:
        return None
    try:
        exp = datetime.strptime(m.group("exp"), "%y%m%d").date()
    except ValueError:
        exp = None
    return {
        "underlying": m.group("root"),
        "expiry": exp,
        "type": "PUT" if m.group("cp") == "P" else "CALL",
        "strike": int(m.group("strike")) / 1000.0,
    }


def classify_ticker(underlying, gp):
    core = set(gp["watchlists"]["core"])
    flex = set(gp["watchlists"]["flex"])
    if underlying in core:
        return "CORE"
    if underlying in flex:
        return "FLEX"
    return "OTHER"


def _dte(expiry):
    if not expiry:
        return None
    return (expiry - datetime.now().date()).days


# --------------------------------------------------------------------------- #
# Build the live picture
# --------------------------------------------------------------------------- #
def build_snapshot():
    gp = load_gameplan()
    summaries = sa.get_account_summaries()
    numbers = {n["mask"]: n for n in sa.get_account_numbers()}
    # Prefer the human account type from gameplan (Schwab API labels IRAs "MARGIN").
    gp_type = {str(a["mask"]): a.get("type") for a in gp.get("accounts", [])}

    # Gather BTC-covered option symbols per account, INCLUDING OTO child orders.
    # An auto-50%-BTC attached to a filled csp entry lives in childOrderStrategies,
    # which get_working_orders flattens away -> scanning it prevents false "NO GTC".
    _LIVE = {"WORKING", "PENDING_ACTIVATION", "QUEUED", "ACCEPTED",
             "AWAITING_CONDITION", "OPEN"}

    def _btc_covered(account_hash):
        syms = set()

        def scan(o):
            if str(o.get("status", "")).upper() in _LIVE:
                for leg in o.get("orderLegCollection", []) or []:
                    if leg.get("instruction") == "BUY_TO_CLOSE":
                        sym = (leg.get("instrument") or {}).get("symbol")
                        if sym:
                            syms.add(sym)
            for c in o.get("childOrderStrategies", []) or []:
                scan(c)

        try:
            for o in sa.get_orders(account_hash, days=5) or []:
                scan(o)
        except Exception:
            pass
        return syms

    btc_by_mask = {}
    for s in summaries:
        n = numbers.get(s["mask"])
        btc_by_mask[s["mask"]] = _btc_covered(n["hashValue"]) if n else set()

    accounts = []
    open_options = []          # each short option position (the wheel legs)
    stock_positions = []       # long shares (assigned stock — the covered-call side)
    ticker_exposure = {}       # combined collateral by underlying
    combined_net_liq = 0.0
    hash_by_mask = {str(n["mask"]): n["hashValue"] for n in (sa.get_account_numbers() or [])}

    for s in summaries:
        net_liq = s["net_liq"] or 0.0
        combined_net_liq += net_liq
        ira_collateral = 0.0
        ira_positions = []

        for p in s["positions"]:
            opt = parse_option_symbol(p["symbol"])
            if opt and p["quantity"] < 0:  # short option = a wheel leg
                contracts = abs(p["quantity"])
                collateral = opt["strike"] * 100 * contracts if opt["type"] == "PUT" else 0.0
                entry_prem = p["average_price"]
                # current mark per share from market value (short MV is negative)
                mv = p["market_value"] or 0.0
                cur_mark = abs(mv) / (100 * contracts) if contracts else None
                pct_to_target = None
                if entry_prem and cur_mark is not None and entry_prem > 0:
                    # profit captured as fraction of entry credit
                    pct_to_target = (entry_prem - cur_mark) / entry_prem

                # Live BUY_TO_CLOSE for this exact option (incl. OTO child orders)?
                has_gtc = p["symbol"] in btc_by_mask.get(s["mask"], set())

                rec = {
                    "account_mask": s["mask"],
                    "symbol": p["symbol"],
                    "underlying": opt["underlying"],
                    "type": opt["type"],
                    "strike": opt["strike"],
                    "expiry": str(opt["expiry"]) if opt["expiry"] else None,
                    "dte": _dte(opt["expiry"]),
                    "contracts": contracts,
                    "entry_premium": entry_prem,
                    "current_mark": round(cur_mark, 3) if cur_mark is not None else None,
                    "pct_to_50_target": round(pct_to_target, 3) if pct_to_target is not None else None,
                    "collateral": collateral,
                    "tier": classify_ticker(opt["underlying"], gp),
                    "has_gtc_exit": has_gtc,
                }
                open_options.append(rec)
                ira_positions.append(rec)
                ira_collateral += collateral
                ticker_exposure[opt["underlying"]] = ticker_exposure.get(opt["underlying"], 0.0) + collateral

            elif (not opt) and p["quantity"] > 0:   # long shares = assigned stock (CC side)
                shares = p["quantity"]
                basis = p["average_price"]               # Schwab raw avg = assignment strike
                eff = effective_stock_basis(hash_by_mask.get(str(s["mask"])), p["symbol"], basis)
                cost_basis = eff if eff is not None else basis
                mv = p["market_value"] or 0.0
                cur_px = (mv / shares) if shares else None
                unreal = (mv - cost_basis * shares) if (cost_basis is not None) else None
                stock_positions.append({
                    "account_mask": s["mask"],
                    "symbol": p["symbol"],
                    "shares": shares,
                    "avg_price": basis,                  # Schwab raw (assignment strike)
                    "effective_basis": eff,              # strike - assigned-put premium
                    "current_price": round(cur_px, 2) if cur_px is not None else None,
                    "market_value": round(mv, 2),
                    "unrealized_pl": round(unreal, 2) if unreal is not None else None,
                    "tier": classify_ticker(p["symbol"], gp),
                })

        accounts.append({
            "mask": s["mask"],
            "type": gp_type.get(s["mask"]) or s["type"],
            "net_liq": net_liq,
            "cash": s["cash"],
            "committed_collateral": ira_collateral,
            "concentration_pct": (ira_collateral / net_liq) if net_liq else None,
            "positions": ira_positions,
        })

    combined_collateral = sum(a["committed_collateral"] for a in accounts)
    deployed_pct = (combined_collateral / combined_net_liq) if combined_net_liq else 0.0
    cash_reserve_pct = 1 - deployed_pct

    return {
        "as_of": datetime.now().isoformat(timespec="seconds"),
        "gameplan": gp,
        "combined_net_liq": combined_net_liq,
        "combined_collateral": combined_collateral,
        "deployed_pct": deployed_pct,
        "cash_reserve_pct": cash_reserve_pct,
        "accounts": accounts,
        "open_options": open_options,
        "stock_positions": stock_positions,
        "ticker_exposure": ticker_exposure,
    }


def effective_stock_basis(account_hash, symbol, avg_price):
    """Effective cost basis for assigned shares = the assignment strike (Schwab's
    avg_price) minus the premium collected on the put that was assigned. Derived from
    the SELL_TO_OPEN of the matching-strike put in the transaction history. Falls back
    to avg_price if no matching put is found or on any error."""
    if avg_price is None or not account_hash:
        return avg_price
    try:
        txns = sa.get_transactions(account_hash, days=120) or []
    except Exception:
        return avg_price
    best = None  # (tradeDate, premium) of the most recent matching-strike put sale
    for t in txns:
        for it in t.get("transferItems", []) or []:
            instr = it.get("instrument", {}) or {}
            info = parse_option_symbol(instr.get("symbol", ""))
            if (info and info["underlying"] == symbol.upper() and info["type"] == "PUT"
                    and abs((info["strike"] or 0) - avg_price) < 0.01
                    and (it.get("amount") or 0) < 0            # SELL_TO_OPEN (sold => negative)
                    and it.get("price")):
                d = str(t.get("tradeDate", ""))
                if best is None or d > best[0]:
                    best = (d, it["price"])
    return round(avg_price - best[1], 2) if best else avg_price


def compute_program_recovery(gp):
    """Has the strategy paid for itself? Cumulative NET option premium (SELL_TO_OPEN
    credits - BUY_TO_CLOSE debits - fees, option legs only; equity conversions like
    assignments excluded) vs the one-time MarketMoves 'Capital Flywheel' tuition."""
    import schwab_accounts as sa
    prog = (gp or {}).get("program", {})
    cost = float(prog.get("cost", 12000))
    opt_net = 0.0
    dates = []
    for acc in (sa.get_account_numbers() or []):
        try:
            txns = sa.get_transactions(acc["hashValue"], days=365) or []
        except Exception:
            txns = []
        for t in txns:
            items = t.get("transferItems", []) or []
            if any((it.get("instrument", {}) or {}).get("assetType") == "OPTION" for it in items):
                opt_net += (t.get("netAmount", 0) or 0)
                d = str(t.get("tradeDate", ""))[:10]
                if d:
                    dates.append(d)
    recovered = round(opt_net, 2)
    return {
        "program_cost": cost,
        "provider": prog.get("provider", "MarketMoves"),
        "net_premium_collected": recovered,
        "recovered_pct": round(recovered / cost * 100, 1) if cost else None,
        "to_break_even": round(max(cost - recovered, 0.0), 2),
        "paid_off": recovered >= cost,
        "since": min(dates) if dates else None,
        "as_of": datetime.now().isoformat(timespec="seconds"),
    }


def _has_matching_btc(symbol, working_orders):
    for o in working_orders:
        for leg in o.get("legs", []):
            if leg.get("symbol") == symbol and str(leg.get("instruction", "")).upper() in (
                    "BUY_TO_CLOSE", "BUY_TO_OPEN"):  # BTC is the exit; guard both spellings
                return True
    return False


# --------------------------------------------------------------------------- #
# Guardrail audit against the Master Operating Plan hard rules
# --------------------------------------------------------------------------- #
def audit(snap):
    gp = snap["gameplan"]
    rules = gp["position_rules"]
    cap = gp["capital"]
    checks = []

    def add(name, status, detail):
        checks.append({"check": name, "status": status, "detail": detail})

    nlv = snap["combined_net_liq"]

    # Cash reserve floor (30%)
    floor = cap["cash_reserve_floor_pct"]
    cr = snap["cash_reserve_pct"]
    add("Cash reserve >= 30%",
        "PASS" if cr >= floor else "FAIL",
        f"{cr*100:.1f}% (target {cap['cash_reserve_target_pct']*100:.0f}%, floor {floor*100:.0f}%)")

    # Deployment ceiling (70% absolute, 50% normal)
    dep = snap["deployed_pct"]
    if dep <= cap["deployed_normal_max_pct"]:
        st = "PASS"
    elif dep <= cap["deployed_absolute_max_pct"]:
        st = "WARN"
    else:
        st = "FAIL"
    add("Deployment <= 70% (normal 50%)", st,
        f"{dep*100:.1f}% deployed")

    # Position counts
    total_positions = len(snap["open_options"])
    add(f"Positions <= {rules['max_positions']}",
        "PASS" if total_positions <= rules["max_positions"] else "FAIL",
        f"{total_positions} open option positions")

    flex_count = sum(1 for o in snap["open_options"] if o["tier"] == "FLEX")
    add(f"Flex positions <= {rules['max_flex_positions']}",
        "PASS" if flex_count <= rules["max_flex_positions"] else "FAIL",
        f"{flex_count} flex positions")

    # Combined ticker cap (10%)
    tcap = rules["max_single_ticker_combined_pct"]
    for tk, exp in sorted(snap["ticker_exposure"].items(), key=lambda x: -x[1]):
        pct = (exp / nlv) if nlv else 0
        add(f"Ticker {tk} <= {tcap*100:.0f}% combined",
            "PASS" if pct <= tcap else "FAIL",
            f"{pct*100:.1f}% (${exp:,.0f})")

    # Per-IRA concentration (25%)
    icap = rules["max_single_ira_concentration_pct"]
    for a in snap["accounts"]:
        c = a["concentration_pct"]
        if c is None:
            continue
        add(f"IRA *{a['mask']} concentration <= {icap*100:.0f}%",
            "PASS" if c <= icap else "FAIL",
            f"{c*100:.1f}% committed")

    # OTHER-tier positions (off approved watchlist)
    for o in snap["open_options"]:
        if o["tier"] == "OTHER":
            add(f"{o['underlying']} on approved watchlist", "WARN",
                "position is not on Core/Flex list (manage-only, no new entries)")

    return checks


def management_flags(snap):
    """Section C - existing-position action items."""
    gp = snap["gameplan"]
    flags = []
    for o in snap["open_options"]:
        # Missing GTC exit (the #1 reconciliation miss) — PUTS only. A covered call's
        # 50% BTC is mode-dependent (churn attaches it; trend_expansion/--no-btc runs
        # it to the strike on purpose), so a call without a GTC is not a miss.
        if o["type"] == "PUT" and not o["has_gtc_exit"]:
            flags.append(("ACTION", f"*{o['account_mask']} {o['underlying']} "
                          f"{o['strike']:g}P "
                          f"exp {o['expiry']}: NO working 50% GTC buy-to-close found -> set it."))
        # At/through 50% profit target
        p = o["pct_to_50_target"]
        if p is not None and p >= gp["exit_rules"]["profit_gtc_pct"]:
            flags.append(("DO_NOW", f"*{o['account_mask']} {o['underlying']} "
                          f"at {p*100:.0f}% of max profit -> close (>=50% target)."))
        elif p is not None and p >= 0.25 and o["dte"] is not None and o["dte"] >= 25:
            flags.append(("WATCH", f"*{o['account_mask']} {o['underlying']} "
                          f"at {p*100:.0f}% profit early -> fast-exit candidate."))
        # Time exit (21 DTE)
        if o["dte"] is not None and o["dte"] <= gp["exit_rules"]["time_exit_dte"]:
            flags.append(("WATCH", f"*{o['account_mask']} {o['underlying']} "
                          f"{o['dte']} DTE -> approaching 21-DTE time-exit window."))
    return flags


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def render(snap, checks, flags):
    L = []
    L.append("=" * 68)
    L.append(f"ARISTOTLE v4.0 - LIVE RECONCILIATION   {snap['as_of']}")
    L.append("  ADVISORY ONLY - measured against your Master Operating Plan")
    L.append("=" * 68)

    # A. Snapshot
    L.append("\n[A] PORTFOLIO SNAPSHOT")
    L.append(f"  Combined Net Liq : ${snap['combined_net_liq']:,.2f}")
    L.append(f"  Deployed         : {snap['deployed_pct']*100:5.1f}%  "
             f"(${snap['combined_collateral']:,.0f} collateral)")
    L.append(f"  Cash reserve     : {snap['cash_reserve_pct']*100:5.1f}%  "
             f"(target 50% / floor 30%)")
    for a in snap["accounts"]:
        conc = f"{a['concentration_pct']*100:.1f}%" if a["concentration_pct"] is not None else "n/a"
        cash = f"${a['cash']:,.0f}" if a["cash"] is not None else "n/a"
        L.append(f"    *{a['mask']} {a['type'] or '':<18} "
                 f"net liq ${a['net_liq']:>11,.0f}  cash {cash:>12}  conc {conc}")

    # Cash-state permission
    cr = snap["cash_reserve_pct"] * 100
    if cr > 70: state = "very cash-heavy -> A+, A, qualified B"
    elif cr >= 50: state = "target/moderate -> A+ and A"
    elif cr >= 30: state = "aggressively deployed -> A+ only"
    else: state = "BELOW HARD RESERVE -> NO new entries"
    L.append(f"  Cash-state rule  : {state}")

    # C. Positions
    L.append(f"\n[C] OPEN POSITIONS ({len(snap['open_options'])})")
    if not snap["open_options"]:
        L.append("  (none)")
    for o in snap["open_options"]:
        gtc = "GTC OK" if o["has_gtc_exit"] else "!! NO GTC"
        prog = f"{o['pct_to_50_target']*100:4.0f}%" if o["pct_to_50_target"] is not None else "  n/a"
        L.append(f"  *{o['account_mask']} {o['tier']:<5} {o['underlying']:<5} "
                 f"{o['strike']:>7g}{'P' if o['type']=='PUT' else 'C'} "
                 f"{o['contracts']}x  {str(o['dte'])+'DTE':>6}  "
                 f"entry ${o['entry_premium']}  prog {prog}  {gtc}")

    # Guardrails
    L.append("\n[G] GUARDRAIL AUDIT (Master Plan hard rules)")
    order = {"FAIL": 0, "WARN": 1, "PASS": 2}
    for c in sorted(checks, key=lambda x: order.get(x["status"], 3)):
        mark = {"PASS": "OK ", "WARN": "!! ", "FAIL": "XX "}.get(c["status"], "?? ")
        L.append(f"  {mark}{c['check']:<34} {c['detail']}")

    # Action items
    L.append("\n[H] ACTION ITEMS")
    if not flags:
        L.append("  (nothing flagged - hold / wait for qualified setups)")
    prio = {"DO_NOW": 0, "ACTION": 1, "WATCH": 2}
    for kind, msg in sorted(flags, key=lambda x: prio.get(x[0], 3)):
        L.append(f"  [{kind:<6}] {msg}")

    L.append("\n" + "=" * 68)
    L.append("Reminder: Aristotle stages tickets; YOU place every order. Not advice.")
    L.append("=" * 68)
    return "\n".join(L)


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Aristotle live reconciliation")
    ap.add_argument("--json", action="store_true", help="machine-readable only")
    ap.add_argument("--save", action="store_true", help="write to state/")
    ap.add_argument("--push", action="store_true", help="push snapshot to Supabase (for the dashboard)")
    args = ap.parse_args()

    snap = build_snapshot()
    checks = audit(snap)
    flags = management_flags(snap)

    payload = {
        "snapshot": {k: v for k, v in snap.items() if k != "gameplan"},
        "guardrails": checks,
        "action_items": [{"priority": k, "message": m} for k, m in flags],
    }

    # 5% pacing + deployment radar (best-effort; never break the core snapshot/push).
    try:
        import pacing
        payload["pacing"] = pacing.compute_pacing(snap)
    except Exception as e:
        print(f"[WARN] pacing compute skipped: {e}")

    # Program break-even: cumulative premium vs the MarketMoves tuition (best-effort).
    try:
        payload["program_recovery"] = compute_program_recovery(snap.get("gameplan"))
    except Exception as e:
        print(f"[WARN] program recovery skipped: {e}")

    if args.save:
        STATE_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        (STATE_DIR / f"reconcile_{stamp}.json").write_text(json.dumps(payload, indent=2, default=str))
        (STATE_DIR / "latest.json").write_text(json.dumps(payload, indent=2, default=str))

    if args.push:
        try:
            import supabase_sync
            supabase_sync.push_snapshot(json.loads(json.dumps(payload, default=str)))
        except Exception as e:
            print(f"[WARN] push skipped: {e}")

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(render(snap, checks, flags))


if __name__ == "__main__":
    main()
