"""
pullback.py - Pullback & assignment playbook checks (gameplan.assignment_playbook,
correction_protocol.drawdown_buckets / macro_regime). READ-ONLY; places nothing.

Adds to every reconcile:
  * QQQ drawdown bucket (dip / correction / bear) and whether pullback core-only mode is on
  * Macro regime from public FRED data (fed funds + unemployment trend)
  * Pre-assignment check: would assigning in-the-money puts leave room for a bottom layer?
  * Covered-call timing per held stock, by its Sandwich path (income_first / balanced / hold_for_upside)
  * Cost-basis tracker: adjusted basis vs price, and months to break-even at the mentor's ~10%/mo pace

    python pullback.py          # print the report
    python pullback.py --json
"""
import csv
import io
import json
import urllib.request
from datetime import date

import schwab_bridge as mkt

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"


def _rsi14(closes):
    n = 14
    if len(closes) <= n:
        return None
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, n + 1)]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, n + 1)]
    ag, al = sum(gains) / n, sum(losses) / n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
    return 100.0 if al == 0 else 100 - 100 / (1 + ag / al)


def _daily_closes(symbol, years=1):
    c = mkt.get_price_history(symbol, period_type="year", period=years, frequency_type="daily", frequency=1) or []
    return [x["close"] for x in c if x.get("close") is not None], [x.get("high") for x in c if x.get("high") is not None]


def qqq_drawdown(gp):
    closes, highs = _daily_closes("QQQ", 1)
    q = (mkt.get_quotes(["QQQ"]) or {}).get("QQQ", {})
    px = q.get("price") or (closes[-1] if closes else None)
    if not highs or px is None:
        return {"status": "UNAVAILABLE"}
    hi = max(highs + [px])
    dd = (px / hi - 1) * 100
    bucket = None
    for b in sorted(gp["correction_protocol"].get("drawdown_buckets", []), key=lambda b: b["qqq_from_52w_high_pct"]):
        if dd <= b["qqq_from_52w_high_pct"]:
            bucket = b
            break
    return {"status": "OK", "price": round(px, 2), "high_52w": round(hi, 2), "drawdown_pct": round(dd, 1),
            "bucket": bucket["name"] if bucket else "none",
            "bucket_frequency": bucket["historical_frequency"] if bucket else None,
            "core_only": bool(bucket) and gp["correction_protocol"].get("pullback_core_only", False)}


def _fred(series):
    req = urllib.request.Request(FRED.format(series))  # FRED stalls on custom/browser user agents
    with urllib.request.urlopen(req, context=mkt.get_ssl_context(), timeout=20) as r:
        rows = list(csv.reader(io.StringIO(r.read().decode("utf-8"))))
    out = []
    for d, v in rows[1:]:
        try:
            out.append((d, float(v)))
        except ValueError:
            pass
    return out


def macro_regime():
    try:
        ff, ur = _fred("FEDFUNDS"), _fred("UNRATE")
    except Exception as e:
        return {"status": "UNAVAILABLE", "error": type(e).__name__}
    ff12 = ff[-13:]
    rate_change = ff12[-1][1] - ff12[0][1]
    rate_rising = rate_change >= 0.75
    ur12 = [v for _, v in ur[-12:]]
    ur3 = sum(v for _, v in ur[-3:]) / 3
    ur_gap = ur3 - min(ur12)
    unemp_rising = ur_gap >= 0.5
    n = int(rate_rising) + int(unemp_rising)
    regime = ["CLEAR", "WATCH", "CAUTION"][n]
    return {"status": "OK", "regime": regime,
            "fed_funds": ff[-1][1], "fed_funds_asof": ff[-1][0], "fed_funds_12m_change": round(rate_change, 2), "rate_rising": rate_rising,
            "unemployment": ur[-1][1], "unemployment_asof": ur[-1][0], "unemployment_3m_vs_12m_low": round(ur_gap, 2), "unemployment_rising": unemp_rising}


def assignment_check(snap, gp, prices):
    nlv = snap["combined_net_liq"] or 0.0
    pr = gp["position_rules"]
    caps = pr.get("ticker_combined_cap_overrides", {})
    layer = pr.get("max_single_entry_pct", 0.10) * nlv * 0.5   # room for at least a half-size layer
    by_ticker = {}
    for o in snap["open_options"]:
        if o["type"] != "PUT":
            continue
        u = o["underlying"]
        px = prices.get(u)
        itm = px is not None and px < o["strike"]
        t = by_ticker.setdefault(u, {"itm_puts": [], "itm_shares": 0, "itm_cost": 0.0})
        if itm:
            t["itm_puts"].append(f"{o['strike']:g}P x{o['contracts']:.0f} {o['expiry']}")
            t["itm_shares"] += int(o["contracts"] * 100)
            t["itm_cost"] += o["strike"] * 100 * o["contracts"]
    out = []
    for u, t in by_ticker.items():
        if not t["itm_puts"]:
            continue
        cap = caps.get(u, pr["max_single_ticker_combined_pct"]) * nlv
        exposure = snap["ticker_exposure"].get(u, 0.0)
        room = cap - exposure
        decaying = u in set(gp.get("assignment_playbook", {}).get("decaying_or_inverse_income_first_only", []))
        if decaying:
            status = "INCOME_FIRST_ONLY"   # no bottom layer on a decaying / inverse fund
        else:
            status = "OVER_CAP" if room < 0 else ("NO_BOTTOM_LAYER" if room < layer else "LAYER_OK")
        out.append({"ticker": u, "itm_puts": t["itm_puts"], "shares_if_assigned": t["itm_shares"],
                    "cost_if_assigned": round(t["itm_cost"]), "ticker_exposure": round(exposure),
                    "ticker_cap": round(cap), "room_for_puts": round(room), "status": status})
    return out


def cc_timing(snap, gp, prices, changes, rsis):
    ap = gp.get("assignment_playbook", {})
    paths, decaying = ap.get("ticker_paths", {}), set(ap.get("decaying_or_inverse_income_first_only", []))
    green, rsi_trig = ap.get("green_day_trigger_pct", 2.0), ap.get("hold_rsi_trigger", 65)
    calls = {}
    for o in snap["open_options"]:
        if o["type"] == "CALL":
            calls[o["underlying"]] = calls.get(o["underlying"], 0) + int(o["contracts"] * 100)
    out = []
    for s in snap["stock_positions"]:
        u = s["symbol"]
        path = "income_first" if u in decaying else paths.get(u, ap.get("default_path", "balanced"))
        shares = int(s["shares"])
        uncovered = shares - calls.get(u, 0)
        chg, rsi = changes.get(u), rsis.get(u)
        if uncovered < 100:
            action, why = "COVERED", f"all {shares} shares already have calls"
        elif path == "income_first":
            action, why = "SELL_CALLS_NOW", "Income First: sell calls right away"
        elif path == "balanced":
            ok = chg is not None and chg >= green
            action = "SELL_CALLS_NOW" if ok else "WAIT"
            why = f"Balanced: sell into a pop (today {chg:+.1f}% vs +{green:g}% trigger)" if chg is not None else "Balanced: no quote"
        else:
            ok = rsi is not None and rsi >= rsi_trig
            action = "SELL_CALLS_NOW" if ok else "WAIT"
            why = f"Hold for Upside: daily RSI {rsi:.0f} vs {rsi_trig} trigger" if rsi is not None else "Hold for Upside: no RSI"
        basis, px = s.get("effective_basis"), prices.get(u)
        gap = (basis - px) if (basis and px) else None
        months = (gap / (basis * 0.10)) if (gap and gap > 0) else 0 if gap is not None else None
        out.append({"ticker": u, "account": s.get("account_mask"), "shares": shares, "uncovered_shares": max(uncovered, 0),
                    "path": path, "action": action, "why": why, "price": px, "day_change_pct": chg, "rsi_daily": round(rsi, 1) if rsi else None,
                    "adjusted_basis": basis, "basis_gap": round(gap, 2) if gap is not None else None,
                    "months_to_breakeven_at_10pct": round(months, 1) if months is not None else None})
    return out


def build(snap):
    gp = snap["gameplan"] if "gameplan" in snap else json.load(open("gameplan.json", encoding="utf-8"))
    tickers = sorted({o["underlying"] for o in snap["open_options"]} | {s["symbol"] for s in snap["stock_positions"]})
    q = mkt.get_quotes(tickers) or {}
    prices = {t: q[t]["price"] for t in tickers if t in q and q[t].get("price")}
    changes = {t: q[t]["change_percent"] for t in tickers if t in q and q[t].get("change_percent") is not None}
    rsis = {}
    for s in snap["stock_positions"]:
        closes, _ = _daily_closes(s["symbol"], 1)
        if s["symbol"] in prices:
            closes = closes + [prices[s["symbol"]]]
        rsis[s["symbol"]] = _rsi14(closes)
    return {"as_of": date.today().isoformat(),
            "drawdown": qqq_drawdown(gp),
            "macro": macro_regime(),
            "assignment_check": assignment_check(snap, gp, prices),
            "covered_calls": cc_timing(snap, gp, prices, changes, rsis)}


def render(p):
    L = ["", "[P] PULLBACK & ASSIGNMENT PLAYBOOK"]
    d = p["drawdown"]
    if d.get("status") == "OK":
        L.append(f"  QQQ {d['price']} is {d['drawdown_pct']:+.1f}% from its 52-week high ({d['high_52w']}) -> bucket: {d['bucket'].upper()}"
                 + ("  | CORE-ONLY entries" if d["core_only"] else ""))
    m = p["macro"]
    if m.get("status") == "OK":
        L.append(f"  Macro: {m['regime']}  (fed funds {m['fed_funds']}% , 12m {m['fed_funds_12m_change']:+.2f}; unemployment {m['unemployment']}%, 3m vs 12m low {m['unemployment_3m_vs_12m_low']:+.2f})")
    else:
        L.append("  Macro: unavailable")
    for a in p["assignment_check"]:
        L.append(f"  Assignment check {a['ticker']}: {', '.join(a['itm_puts'])} -> {a['shares_if_assigned']} sh / ${a['cost_if_assigned']:,}; "
                 f"room under cap ${a['room_for_puts']:,} -> {a['status']}")
    for c in p["covered_calls"]:
        L.append(f"  Covered calls {c['ticker']} (*{c['account']}, {c['shares']} sh, {c['path']}): {c['action']} - {c['why']}"
                 + (f" | basis {c['adjusted_basis']} vs {c['price']}" if c.get("adjusted_basis") else ""))
    return "\n".join(L)


if __name__ == "__main__":
    import argparse
    import reconcile as rec
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    p = build(rec.build_snapshot())
    print(json.dumps(p, indent=2, default=str) if a.json else render(p))
