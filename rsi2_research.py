"""
rsi2_research.py - Connors RSI(2) research tool (READ-ONLY, not wired into gates)
==================================================================================
Evaluates whether RSI(2) extremes deserve a place in the Flywheel (Rev 1.5
candidate). Touches NOTHING in gameplan.json and places nothing.

Usage:
    python rsi2_research.py now DFEN SOXL TQQQ QQQ      # current D/W/M RSI(2) + trend
    python rsi2_research.py monthly SOXL                # monthly RSI2 <10/<5 signal history
    python rsi2_research.py daily SOXL                  # daily RSI2 vs red-day rule, CSP proxy

Definitions:
    RSI(2)      Wilder RSI, period 2 (Connors).
    Trend       daily: close > 200-day SMA (Connors).  monthly: close > 10-month SMA.
    CSP proxy   a put struck `otm`% below the signal close, expiring `hold` trading
                days later, "survives" if the close then is >= strike. Not a P&L
                model (no premium/IV) - it measures how often the entry was safe.
"""

import argparse
import statistics as st
import sys
from datetime import datetime

import schwab_bridge as mkt


def rsi(closes, n=2):
    """Wilder RSI series (None until seeded)."""
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, n + 1)]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, n + 1)]
    ag, al = sum(gains) / n, sum(losses) / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def sma(vals, n, i):
    return sum(vals[i - n + 1:i + 1]) / n if i >= n - 1 else None


def candles(symbol, freq):
    period = 20 if freq in ("daily", "weekly", "monthly") else 1
    c = mkt.get_price_history(symbol, period_type="year", period=period,
                              frequency_type=freq, frequency=1)
    if not c:
        sys.exit(f"[X] no {freq} data for {symbol}")
    return [x for x in c if x["close"] is not None]


def pct(a, b):
    return (b / a - 1) * 100


# --------------------------------------------------------------------------- #
def cmd_now(symbols):
    print(f"RSI(2) snapshot  {datetime.now():%Y-%m-%d %H:%M}  (monthly = candle incl. today)")
    print(f"{'SYM':6} {'close':>9} {'D-RSI2':>7} {'W-RSI2':>7} {'M-RSI2':>7}  "
          f"{'>200d':>6} {'>10mo':>6}  flags")
    for s in symbols:
        d, w, m = candles(s, "daily"), candles(s, "weekly"), candles(s, "monthly")
        dc, wc, mc = [x["close"] for x in d], [x["close"] for x in w], [x["close"] for x in m]
        dr, wr, mr = rsi(dc)[-1], rsi(wc)[-1], rsi(mc)[-1]
        s200 = sma(dc, 200, len(dc) - 1)
        s10 = sma(mc, 10, len(mc) - 1)
        up_d = s200 is not None and dc[-1] > s200
        up_m = s10 is not None and mc[-1] > s10
        flags = []
        for lbl, r in (("D", dr), ("W", wr), ("M", mr)):
            if r is not None and r < 5:
                flags.append(f"{lbl}<5")
            elif r is not None and r < 10:
                flags.append(f"{lbl}<10")
        # A monthly RSI2 extreme is almost always below its own 10-mo SMA (history
        # shows every SOXL/TQQQ/DFEN signal was), so only the daily 200d is a usable filter.
        if flags and not up_d:
            flags.append("below 200d")
        f = lambda r: f"{r:7.1f}" if r is not None else "    n/a"
        print(f"{s:6} {dc[-1]:9.2f} {f(dr)} {f(wr)} {f(mr)}  "
              f"{'yes' if up_d else 'NO':>6} {'yes' if up_m else 'NO':>6}  {' '.join(flags)}")


# --------------------------------------------------------------------------- #
def cmd_monthly(symbol, thresh):
    m = candles(symbol, "monthly")
    c = [x["close"] for x in m]
    r = rsi(c)
    print(f"{symbol} monthly RSI(2) < {thresh}  ({m[0]['datetime'][:7]} .. {m[-1]['datetime'][:7]}, "
          f"{len(m)} months)")
    print(f"{'month':8} {'RSI2':>5} {'close':>9} {'>10mo':>6} {'+3m':>7} {'+6m':>7} "
          f"{'+12m':>7} {'maxDD':>7}")
    rows = []
    for i in range(2, len(c)):
        if r[i] is None or r[i] >= thresh:
            continue
        s10 = sma(c, 10, i)
        fw = {k: (pct(c[i], c[i + k]) if i + k < len(c) else None) for k in (3, 6, 12)}
        dd = min(pct(c[i], x["low"]) for x in m[i + 1:i + 13]) if i + 1 < len(m) else None
        rows.append((fw, dd))
        g = lambda v: f"{v:+6.0f}%" if v is not None else "      -"
        print(f"{m[i]['datetime'][:7]:8} {r[i]:5.1f} {c[i]:9.2f} "
              f"{('yes' if s10 and c[i] > s10 else 'NO'):>6} {g(fw[3])} {g(fw[6])} "
              f"{g(fw[12])} {g(dd)}")
    for k in (3, 6, 12):
        v = [f[k] for f, _ in rows if f[k] is not None]
        if v:
            print(f"  +{k}m: n={len(v)} median {st.median(v):+.0f}%  "
                  f"win {sum(x > 0 for x in v) / len(v):.0%}")
    print("  maxDD = worst intramonth low over the following 12 months (early-entry pain)")


# --------------------------------------------------------------------------- #
def cmd_daily(symbol, otm, hold):
    d = candles(symbol, "daily")
    c = [x["close"] for x in d]
    r = rsi(c)

    def stats(name, idx):
        idx = [i for i in idx if i + hold < len(c)]
        if not idx:
            print(f"  {name:34} n=0")
            return
        surv = sum(c[i + hold] >= c[i] * (1 - otm / 100) for i in idx) / len(idx)
        fwd = [pct(c[i], c[i + hold]) for i in idx]
        dd = [min(pct(c[i], x["low"]) for x in d[i + 1:i + hold + 1]) for i in idx]
        print(f"  {name:34} n={len(idx):4}  survive {surv:5.0%}  "
              f"median fwd {st.median(fwd):+6.1f}%  median worst {st.median(dd):+6.1f}%")

    base = range(200, len(c))
    up = [i for i in base if c[i] > sma(c, 200, i)]
    red3 = [i for i in up if pct(c[i - 1], c[i]) <= -3]
    r10 = [i for i in up if r[i] is not None and r[i] < 10]
    r5 = [i for i in up if r[i] is not None and r[i] < 5]
    both = [i for i in red3 if r[i] is not None and r[i] < 10]
    print(f"{symbol} daily  {d[200]['datetime'][:10]} .. {d[-1]['datetime'][:10]}  "
          f"CSP proxy: strike {otm}% OTM, {hold} trading days")
    stats("all days", list(base))
    stats("uptrend (>200d) any day", up)
    stats("uptrend + red day <= -3% (current)", red3)
    stats("uptrend + RSI2 < 10", r10)
    stats("uptrend + RSI2 < 5", r5)
    stats("uptrend + red<=-3% AND RSI2<10", both)
    print("  (signals overlap/cluster; n counts days, not independent trades)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["now", "monthly", "daily"])
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--thresh", type=float, default=10)
    ap.add_argument("--otm", type=float, default=10, help="CSP proxy strike %% below close")
    ap.add_argument("--hold", type=int, default=25, help="CSP proxy trading days to expiry")
    a = ap.parse_args()
    if a.mode == "now":
        cmd_now([s.upper() for s in a.symbols])
    for s in a.symbols:
        if a.mode == "monthly":
            cmd_monthly(s.upper(), a.thresh)
        elif a.mode == "daily":
            cmd_daily(s.upper(), a.otm, a.hold)


if __name__ == "__main__":
    main()
