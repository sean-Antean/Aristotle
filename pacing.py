"""pacing.py - Aristotle 5% monthly pacing + deployment radar
==============================================================
Makes "cash heavy hurts" a number. Answers, for the current month:
  - how much option premium have I NET collected vs the 5% target,
  - am I ahead or behind pace for this point in the month,
  - the dollar gap, and how much of my idle cash could still be working.

DECISION SUPPORT ONLY. It never says "force a trade." Cash is a valid position;
the 5% is a target, not a mandate (Master Operating Plan, objective.no_force).
The gap is shown so you deploy MORE into setups that already qualify -- not so
you lower the bar.

Usage:
    python pacing.py            # print the radar
    python pacing.py --json     # machine-readable (used by the dashboard push)
"""
import calendar
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import schwab_accounts as acct
import schwab_bridge as mkt
import reconcile as rec

HERE = Path(__file__).parent


def load_gp():
    return json.loads((HERE / "gameplan.json").read_text(encoding="utf-8"))


def _now_utc():
    return datetime.now(timezone.utc)


def _month_start_utc():
    n = _now_utc()
    return datetime(n.year, n.month, 1, tzinfo=timezone.utc)


def _parse_dt(t):
    if not t:
        return None
    try:
        return datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except ValueError:
        return None


def mtd_option_premium():
    """Net option premium cashflow this month across both IRAs (SELL_TO_OPEN
    credits minus BUY_TO_CLOSE debits, fees included). Positive = net collected."""
    ms = _month_start_utc()
    days = (_now_utc() - ms).days + 2
    total, n = 0.0, 0
    for a in acct.get_account_numbers() or []:
        txns = acct.get_transactions(a["hashValue"], days=days, types="TRADE") or []
        for tx in txns:
            dt = _parse_dt(tx.get("time") or tx.get("tradeDate"))
            if dt is None or dt < ms:
                continue
            items = tx.get("transferItems", []) or []
            if not any((it.get("instrument") or {}).get("assetType") == "OPTION" for it in items):
                continue
            net = tx.get("netAmount")
            if net is None:
                continue
            total += net
            n += 1
    return round(total, 2), n


def month_start_basis(current_nlv):
    """5% basis = combined month-start net liq. Pull the earliest Supabase
    snapshot dated this month; fall back to current net liq if none exists yet."""
    try:
        cfg = json.loads((HERE / "supabase_config.json").read_text())
        ms = _month_start_utc().isoformat()
        url = (cfg["url"].rstrip("/") + "/rest/v1/snapshots"
               f"?created_at=gte.{ms}&select=combined_net_liq,created_at"
               "&order=created_at.asc&limit=1")
        req = urllib.request.Request(url, headers={
            "apikey": cfg["service_role_key"],
            "Authorization": f"Bearer {cfg['service_role_key']}"})
        rows = json.loads(urllib.request.urlopen(
            req, context=mkt.get_ssl_context(), timeout=20).read())
        if rows and rows[0].get("combined_net_liq"):
            return float(rows[0]["combined_net_liq"]), "month-start snapshot"
    except Exception:
        pass
    return current_nlv, "current net liq (no month-start snapshot yet)"


def compute_pacing(snap=None):
    gp = load_gp()
    ap = gp.get("aggression_profile", {})
    snap = snap or rec.build_snapshot()
    nlv = snap.get("combined_net_liq") or 0.0

    basis, basis_src = month_start_basis(nlv)
    target_pct = ap.get("monthly_return_target_pct", gp["objective"]["monthly_target_pct"] / 100)
    target_dollars = basis * target_pct

    mtd, n_txn = mtd_option_premium()

    now = _now_utc()
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    day = now.day
    expected_by_now = target_dollars * day / days_in_month
    if mtd >= expected_by_now * 1.05:
        pace = "AHEAD"
    elif mtd >= expected_by_now * 0.90:
        pace = "ON PACE"
    else:
        pace = "BEHIND"

    # Open credit still in play (already collected, GTC not yet hit).
    open_credit, credits = 0.0, []
    for p in snap.get("open_options", []):
        if p.get("type") == "PUT" and p.get("entry_premium") and p.get("contracts"):
            c = p["entry_premium"] * 100 * p["contracts"]
            open_credit += c
            credits.append(p["entry_premium"] * 100)
    avg_credit = round(sum(credits) / len(credits), 2) if credits else 150.0

    deployed_pct = snap.get("deployed_pct") or 0.0
    deploy_target = ap.get("deploy_target_pct", 0.60)
    idle_deployable = max(0.0, (deploy_target - deployed_pct) * nlv)

    gap = round(target_dollars - mtd, 2)
    contracts_to_close_gap = int(gap // avg_credit) + 1 if gap > 0 and avg_credit else 0

    return {
        "basis": round(basis, 2), "basis_source": basis_src,
        "target_pct": target_pct, "target_dollars": round(target_dollars, 2),
        "mtd_premium": mtd, "mtd_txn_count": n_txn,
        "pct_of_target": round(mtd / target_dollars, 4) if target_dollars else 0,
        "day": day, "days_in_month": days_in_month,
        "expected_by_now": round(expected_by_now, 2), "pace_status": pace,
        "gap_dollars": gap,
        "open_credit_in_play": round(open_credit, 2),
        "avg_credit_per_contract": avg_credit,
        "contracts_to_close_gap": contracts_to_close_gap,
        "deployed_pct": round(deployed_pct, 4), "deploy_target_pct": deploy_target,
        "idle_deployable": round(idle_deployable, 2),
        "as_of": now.isoformat(timespec="seconds"),
    }


def render(p):
    def dollars(x):
        return f"${x:,.0f}"
    L = ["=" * 60,
         f"5% PACING + DEPLOYMENT RADAR   {p['as_of'][:16].replace('T',' ')}",
         "=" * 60,
         f"  Basis (month-start net liq): {dollars(p['basis'])}  [{p['basis_source']}]",
         f"  Monthly target ({p['target_pct']*100:.0f}%): {dollars(p['target_dollars'])}",
         "",
         f"  Collected MTD (net option premium): {dollars(p['mtd_premium'])}"
         f"  ({p['pct_of_target']*100:.0f}% of target, {p['mtd_txn_count']} trades)",
         f"  Expected by day {p['day']}/{p['days_in_month']}: {dollars(p['expected_by_now'])}"
         f"   ->  {p['pace_status']}"]
    if p["gap_dollars"] > 0:
        L.append(f"  GAP to target: {dollars(p['gap_dollars'])}"
                 f"  ~= {p['contracts_to_close_gap']} more contracts "
                 f"(@ avg {dollars(p['avg_credit_per_contract'])}/ct)")
    else:
        L.append(f"  Target MET (+{dollars(-p['gap_dollars'])} over). "
                 f"Extra is stretch toward 10%.")
    L += ["",
          f"  Deployed: {p['deployed_pct']*100:.0f}%  (target ~{p['deploy_target_pct']*100:.0f}%)",
          f"  Idle cash that could still work: {dollars(p['idle_deployable'])}"
          f"  <- put THIS into qualified setups (layer / assignment mode)",
          f"  Credit already in play (open): {dollars(p['open_credit_in_play'])}",
          "",
          "  Deploy into setups that already qualify. Never force a weak trade to",
          "  hit the number -- a short month on no setups is the plan working.",
          "=" * 60]
    return "\n".join(L)


if __name__ == "__main__":
    import argparse
    a = argparse.ArgumentParser(description="Aristotle 5% pacing radar")
    a.add_argument("--json", action="store_true")
    args = a.parse_args()
    p = compute_pacing()
    if args.json:
        print(json.dumps(p, indent=2, default=str))
    else:
        print(render(p))
