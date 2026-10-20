"""
flash_check.py - Aristotle FLASH CHECK / morning routine
========================================================
Evaluate a potential CSP move against the Master Operating Plan AND your live
portfolio, verdict-first (per v1.1 Section 12). Also scans the watchlist for
premarket A+/A down-day candidates (the 7 AM MST routine).

ADVISORY ONLY. Produces a verdict + a ready-to-place ticket. YOU place the order.
Aristotle computes clouds/RSI from Schwab price history as a strong first pass;
TradingView remains your visual source of truth if you want to confirm.

Usage:
    python flash_check.py SOXL              # full FLASH CHECK on one ticker
    python flash_check.py TQQQ --dte 30
    python flash_check.py --scan            # premarket watchlist scan (A+/A/B)
    python flash_check.py --scan --min -5   # only names down >=5% (A+)
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import schwab_bridge as mkt
import schwab_accounts as acct
import reconcile as rec

CONFIG_DIR = Path(__file__).parent


def load_gp():
    return json.loads((CONFIG_DIR / "gameplan.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# EMA cloud score (daily OR weekly) from Schwab price history
# --------------------------------------------------------------------------- #
def cloud_score(symbol, frequency_type="daily", period=2):
    """Ripster-style 3-cloud score (5/12, 34/50, 72/89). Returns dict."""
    candles = mkt.get_price_history(symbol, period_type="year", period=period,
                                    frequency_type=frequency_type, frequency=1)
    if not candles:
        return {"score": None, "status": "NO_DATA"}
    closes = [c["close"] for c in candles if c["close"] is not None]
    if len(closes) < 90:
        return {"score": None, "status": "INSUFFICIENT", "n": len(closes)}

    def ema(n):
        return mkt.calculate_ema(closes[-max(n * 3, 90):], n)

    fast = ema(5) > ema(12)
    med = ema(34) > ema(50)
    slow = ema(72) > ema(89)
    return {"score": int(fast) + int(med) + int(slow),
            "fast": fast, "medium": med, "slow": slow, "status": "OK"}


def tier_for_move(change_pct, gp):
    """A+/A/B/NO_TRADE from the day's move (RSI checked separately/visually)."""
    if change_pct is None:
        return "UNKNOWN"
    if change_pct <= -5:
        return "A+"
    if change_pct <= -3:
        return "A"
    if change_pct <= -1:
        return "B"
    return "NO_TRADE"  # green / inadequate pullback


def check_intraday_pullback(symbol, gp):
    """TACTICAL_INTRADAY mode — Rev 1.4.

    Returns dict with:
      eligible: bool
      grade: 'TACTICAL_INTRADAY-60m' | 'TACTICAL_INTRADAY-30m' | None
      reasons: list of strings (why rejected, or confirmation)
      session_high: float | None
      pullback_pct: float | None
      candle_timeframe: str | None
    """
    ip = gp.get("intraday_pullback", {})
    if not ip.get("enabled", False):
        return {"eligible": False, "grade": None, "reasons": ["intraday mode disabled"],
                "session_high": None, "pullback_pct": None, "candle_timeframe": None}

    reasons = []

    # 1. Universe check: core tickers only
    allowed = set(ip.get("core_tickers_only", []))
    if symbol not in allowed:
        reasons.append(f"{symbol} not in core_tickers_only for intraday mode")
        return {"eligible": False, "grade": None, "reasons": reasons,
                "session_high": None, "pullback_pct": None, "candle_timeframe": None}

    # 2. Fetch intraday candles (TODAY's session, 30m and 60m)
    # Schwab API: minute frequency only supports 1, 5, 10, 15, 30
    # For 60m, we fetch 30m and aggregate two candles
    # Use startDate/endDate to get TODAY's session, not period=1 (which gives yesterday)
    from datetime import datetime, timedelta
    today = datetime.now().date()
    start_dt = datetime(today.year, today.month, today.day)
    end_dt = start_dt + timedelta(days=1)
    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    
    cand_30_raw = mkt.get_price_history(symbol, period_type="day", period=1,
                                        frequency_type="minute", frequency=30,
                                        start_date=start_ms, end_date=end_ms)
    # Fallback: if no data with startDate, try period=1 (yesterday's data for comparison)
    if not cand_30_raw:
        cand_30_raw = mkt.get_price_history(symbol, period_type="day", period=1,
                                            frequency_type="minute", frequency=30)
    
    cand_30 = cand_30_raw  # 30m candles directly
    # Build 60m candles by aggregating pairs of 30m candles
    cand_60 = []
    if cand_30_raw and len(cand_30_raw) >= 2:
        for i in range(0, len(cand_30_raw) - 1, 2):
            c1 = cand_30_raw[i]
            c2 = cand_30_raw[i + 1]
            cand_60.append({
                "datetime": c1["datetime"],
                "open": c1["open"],
                "high": max(c1["high"], c2["high"]),
                "low": min(c1["low"], c2["low"]),
                "close": c2["close"],
                "volume": (c1["volume"] or 0) + (c2["volume"] or 0),
            })
        # If odd number, drop the last unpaired 30m candle for 60m aggregation

    if not cand_60 or len(cand_60) < 1:
        reasons.append("insufficient 60m intraday data (need 2+ 30m candles)")
        return {"eligible": False, "grade": None, "reasons": reasons,
                "session_high": None, "pullback_pct": None, "candle_timeframe": None}

    # 3. Completed candles only — drop the last candle if market is still open
    # Heuristic: if the last candle's datetime is within the last 5 minutes, it's in-progress
    now = datetime.now()
    def drop_in_progress(candles, minutes=5):
        if not candles:
            return candles
        last_dt_str = candles[-1]["datetime"]
        # Handle both ISO format with timezone and millisecond timestamps
        if isinstance(last_dt_str, (int, float)):
            last_dt = datetime.fromtimestamp(last_dt_str / 1000)
        else:
            # Remove Z suffix and handle timezone
            last_dt_str = str(last_dt_str).replace("Z", "+00:00")
            try:
                last_dt = datetime.fromisoformat(last_dt_str)
            except ValueError:
                # Fallback: try parsing as timestamp
                try:
                    last_dt = datetime.fromtimestamp(int(last_dt_str) / 1000)
                except (ValueError, TypeError):
                    return candles[:-1]  # Can't parse, assume in-progress
        # naive comparison: assume local time matches market time (ET)
        # Also handle case where candle time is in the future (timezone offset)
        time_diff = (now - last_dt).total_seconds()
        if -300 < time_diff < minutes * 60:  # within 5 min window (allow small negative for tz)
            return candles[:-1]
        return candles

    cand_60 = drop_in_progress(cand_60)
    cand_30 = drop_in_progress(cand_30)

    if len(cand_60) < 1:
        reasons.append("no completed 60m candles available")
        return {"eligible": False, "grade": None, "reasons": reasons,
                "session_high": None, "pullback_pct": None, "candle_timeframe": None}

    # 4. Session high = highest high across ALL completed candles today (both 30m and 60m)
    all_candles = cand_60 + cand_30
    session_high = max(c["high"] for c in all_candles if c["high"] is not None)
    current_price = cand_60[-1]["close"] if cand_60 else (cand_30[-1]["close"] if cand_30 else None)

    # 5. Check pullback on preferred timeframe first (60m), then 30m
    min_pullback = ip.get("min_pullback_pct", 1.0)
    preferred = ip.get("preferred_timeframe", "60m")

    # Try preferred first
    ok_60, result_60 = _check_red_pullback_any(cand_60, "60m", session_high, min_pullback)
    if ok_60:
        idx, candle, pullback_pct = result_60
        reasons.append(f"60m red candle (idx {idx}), pullback {pullback_pct:.2f}% from session high ${session_high:.2f}")
        return {"eligible": True, "grade": "TACTICAL_INTRADAY-60m", "reasons": reasons,
                "session_high": session_high, "pullback_pct": pullback_pct, "candle_timeframe": "60m"}

    # Fallback to 30m
    ok_30, result_30 = _check_red_pullback_any(cand_30, "30m", session_high, min_pullback)
    if ok_30:
        idx, candle, pullback_pct = result_30
        reasons.append(f"30m red candle (idx {idx}), pullback {pullback_pct:.2f}% from session high ${session_high:.2f}")
        return {"eligible": True, "grade": "TACTICAL_INTRADAY-30m", "reasons": reasons,
                "session_high": session_high, "pullback_pct": pullback_pct, "candle_timeframe": "30m"}

    # Neither passed
    reasons.append(result_60 if isinstance(result_60, str) else "no 60m data")
    if cand_30:
        reasons.append(result_30 if isinstance(result_30, str) else "no 30m data")
    return {"eligible": False, "grade": None, "reasons": reasons,
            "session_high": session_high, "pullback_pct": None, "candle_timeframe": None}


def _check_red_pullback_any(candles, tf_label, session_high, min_pullback):
    """Scan ALL completed candles for any red candle with valid pullback.
    Returns (ok, msg_or_tuple)."""
    if not candles or len(candles) < 1:
        return False, None
    # Scan from most recent to oldest
    for idx in range(len(candles) - 1, -1, -1):
        candle = candles[idx]
        if candle["close"] < candle["open"]:
            pullback_pct = (session_high - candle["close"]) / session_high * 100
            if pullback_pct >= min_pullback:
                return True, (idx, candle, pullback_pct)
            else:
                return False, f"latest {tf_label} red candle pullback {pullback_pct:.2f}% < {min_pullback}% min"
    return False, f"no red {tf_label} candle found in completed candles"


# --------------------------------------------------------------------------- #
# Sizing headroom against the live portfolio
# --------------------------------------------------------------------------- #
def sizing_headroom(symbol, snap, gp):
    """Max collateral we can add to `symbol` under all caps, and best IRA."""
    nlv = snap["combined_net_liq"] or 0.0
    rules = gp["position_rules"]
    cap = gp["capital"]

    ticker_now = snap["ticker_exposure"].get(symbol, 0.0)
    room_combined = rules["max_single_ticker_combined_pct"] * nlv - ticker_now
    # Multiple-entries rule: any single entry <= max_single_entry_pct. Reach the
    # full ticker cap only by scaling in. The FIRST entry (no existing position)
    # is capped to one entry's size, so 20% is built over 2+ entries, never one fill.
    single_entry = rules.get("max_single_entry_pct",
                             rules["max_single_ticker_combined_pct"]) * nlv
    if ticker_now <= 0:
        room_combined = min(room_combined, single_entry)
    total_committed = snap["combined_collateral"]
    room_deploy = cap["deployed_absolute_max_pct"] * nlv - total_committed
    room_cash = (snap["cash_reserve_pct"] - cap["cash_reserve_floor_pct"]) * nlv

    # Best IRA by remaining 25% concentration room
    best_ira, best_ira_room = None, -1
    for a in snap["accounts"]:
        anlv = a["net_liq"] or 0.0
        room = rules["max_single_ira_concentration_pct"] * anlv - a["committed_collateral"]
        if room > best_ira_room:
            best_ira, best_ira_room = a, room

    max_collateral = max(0.0, min(room_combined, room_deploy, room_cash, best_ira_room))
    return {
        "max_collateral": max_collateral,
        "room_combined": room_combined,
        "room_deploy": room_deploy,
        "room_cash": room_cash,
        "best_ira": best_ira["mask"] if best_ira else None,
        "best_ira_room": best_ira_room,
        "ticker_now": ticker_now,
    }


# --------------------------------------------------------------------------- #
# Strike selection from the live option chain
# --------------------------------------------------------------------------- #
def rank_strikes(symbol, gp, dte=None):
    """Top-N OTM put candidates - one per expiration (~target delta), across the
    flash DTE window, ranked by capital efficiency (ROC/day) so short-dated
    fast-turnover CSPs surface. Returns (list_of_candidates, underlying_price)."""
    tp = gp["trade_params"]
    dmin = tp.get("flash_dte_min", 7)
    dmax = dte or tp.get("flash_dte_max", 45)
    target_delta = tp.get("delta_target", 0.28)
    top_n = tp.get("flash_top_n", 4)
    spread_max = tp.get("spread_max_pct_of_mid", 10)

    chain = mkt.get_option_chains(symbol, days_to_expiration=dmax, strike_count=40)
    if not chain or not chain.get("expiration_dates"):
        return [], None
    under = chain.get("underlying_price")

    per_exp = {}  # best ~target-delta OTM put for each expiration
    for exp in chain["expiration_dates"]:
        for s in exp["strikes"]:
            d = s.get("days_to_expiry")
            strike, prem, delta = s.get("strike"), s.get("mark"), s.get("delta")
            if not strike or not prem or prem <= 0 or d is None:
                continue
            if d < dmin or d > dmax + 5:                # DTE window
                continue
            if under and strike >= under:               # OTM puts only
                continue
            if delta is not None and not (0.15 <= abs(delta) <= 0.40):
                continue                                 # sane CSP delta band
            bid, ask = s.get("bid") or 0, s.get("ask") or 0
            mid = (bid + ask) / 2 if (bid and ask) else prem
            spread_pct = round((ask - bid) / mid * 100, 1) if (mid > 0 and ask and bid) else None
            roc = prem / strike
            dd = abs(abs(delta if delta is not None else 0) - target_delta)
            cand = {
                "exp": exp["date"], "dte": d, "strike": strike, "premium": round(prem, 2),
                "iv": s.get("iv"), "delta": delta, "roc": roc,
                "roc_per_day": roc / d if d else 0,
                "annual_roc": roc * 365 / d if d else 0,
                "oi": s.get("open_interest"), "vol": s.get("volume"),
                "spread_pct": spread_pct, "_dd": dd,
            }
            cur = per_exp.get(exp["date"])
            if cur is None or dd < cur["_dd"]:          # keep nearest-delta per expiration
                per_exp[exp["date"]] = cand

    def liquid(c):
        ok_spread = c["spread_pct"] is None or c["spread_pct"] <= spread_max
        return ok_spread and (c["oi"] or 0) >= 25

    cands = list(per_exp.values())
    # rank: liquid first, then capital efficiency (ROC per day)
    cands.sort(key=lambda c: (liquid(c), c["roc_per_day"]), reverse=True)
    for i, c in enumerate(cands):
        c["liquid"] = liquid(c)
    return cands[:top_n], under


# --------------------------------------------------------------------------- #
# Support levels + trend strength (for the strike-spectrum / assignment mode)
# --------------------------------------------------------------------------- #
def support_levels(symbol, gp):
    """Structure + dynamic support from daily candles: 20-day swing low, 20/50
    EMA. Used to judge whether a strike would put us in at a 'good' level."""
    lookback = gp.get("aggression_profile", {}).get("support_lookback_days", 20)
    candles = mkt.get_price_history(symbol, period_type="year", period=1,
                                    frequency_type="daily", frequency=1)
    if not candles:
        return None
    closes = [c["close"] for c in candles if c.get("close") is not None]
    lows = [c["low"] for c in candles if c.get("low") is not None]
    if not closes or not lows:
        return None
    swing_low = min(lows[-lookback:])
    ema20 = mkt.calculate_ema(closes[-60:], 20) if len(closes) >= 25 else None
    ema50 = mkt.calculate_ema(closes[-150:], 50) if len(closes) >= 55 else None
    return {"swing_low": swing_low, "ema20": ema20, "ema50": ema50, "last": closes[-1]}


def support_label(strike, sup):
    """Where a strike sits vs support. 'At/below' = a good assignment entry."""
    if not sup:
        return "?", False
    sl, e50 = sup.get("swing_low"), sup.get("ema50")
    if sl and strike <= sl:
        return "<20d low", True          # deep-value assignment entry
    if e50 and strike <= e50:
        return "<=50EMA", True           # at/below trend support
    if e50 and strike <= e50 * 1.02:
        return "~50EMA", True            # right at support
    return "above sup", False            # rich strike -> income, not assignment


def trend_is_strong(daily, weekly, gp):
    """STRONG = both daily AND weekly clouds >=2/3 (weekly senior). Gates the
    aggressive/assignment strikes so they never light up on a falling knife."""
    ds, ws = daily.get("score"), weekly.get("score")
    if ds is None or ws is None:
        return False
    return ds >= 2 and ws >= 2


def strike_spectrum(symbol, gp, dte=None):
    """Delta ladder (~0.20..0.40) for the best standard-flywheel expiration,
    each strike annotated vs support + assignment cost basis. Lets the user dial
    premium vs assignment deliberately. Returns (rows, exp_date, under, support)."""
    ap = gp.get("aggression_profile", {})
    deltas = ap.get("strike_spectrum_deltas", [0.20, 0.25, 0.30, 0.35, 0.40])
    tp = gp["trade_params"]
    lo, hi = tp["dte_target_min"], tp["dte_target_max"]      # 30-45 standard window
    chain = mkt.get_option_chains(symbol, days_to_expiration=(dte or hi) + 5,
                                  strike_count=60)
    if not chain or not chain.get("expiration_dates"):
        return [], None, None, None
    under = chain.get("underlying_price")
    sup = support_levels(symbol, gp)

    # Expiration closest to the middle of the standard window (prefer inside it).
    target_dte = dte or (lo + hi) // 2
    best_exp, best_score = None, 1e9
    for exp in chain["expiration_dates"]:
        d = next((s.get("days_to_expiry") for s in exp["strikes"]
                  if s.get("days_to_expiry") is not None), None)
        if d is None:
            continue
        score = abs(d - target_dte) + (0 if lo <= d <= hi else 100)
        if score < best_score:
            best_score, best_exp = score, exp
    if not best_exp:
        return [], None, under, sup

    puts = [s for s in best_exp["strikes"]
            if s.get("strike") and s.get("mark") and s["mark"] > 0
            and (not under or s["strike"] < under)]
    rows, seen = [], set()
    for td in deltas:
        best, bd = None, 1e9
        for s in puts:
            dl = abs(s.get("delta") or 0)
            if dl and abs(dl - td) < bd:
                bd, best = abs(dl - td), s
        if not best or best["strike"] in seen:
            continue
        seen.add(best["strike"])
        strike, prem = best["strike"], best["mark"]
        d = best.get("days_to_expiry")
        roc = prem / strike
        lbl, at_support = support_label(strike, sup)
        rows.append({
            "target_delta": td, "strike": strike, "premium": round(prem, 2),
            "delta": best.get("delta"), "roc": roc,
            "annual_roc": roc * 365 / d if d else 0, "dte": d,
            "iv": best.get("iv"), "oi": best.get("open_interest"),
            "assign_basis": round(strike - prem, 2),
            "support": lbl, "at_support": at_support,
        })
    rows.sort(key=lambda r: r["strike"])
    return rows, best_exp["date"], under, sup


def pick_assignment_strike(spectrum, trend_strong, gp):
    """Balanced assignment pick: richest strike (highest delta up to delta_max)
    that sits AT/BELOW support AND only when the trend is strong. Never forces
    one — returns None if nothing qualifies (that's the discipline)."""
    am = gp.get("aggression_profile", {}).get("assignment_mode", {})
    if not am.get("enabled") or not spectrum:
        return None
    if am.get("requires_strong_trend", True) and not trend_strong:
        return None
    dmin, dmax = am.get("delta_min", 0.30), am.get("delta_max", 0.40)
    need_support = am.get("requires_strike_at_or_below_support", True)
    qualifying = [r for r in spectrum
                  if r["delta"] is not None and dmin <= abs(r["delta"]) <= dmax
                  and (r["at_support"] or not need_support)]
    if not qualifying:
        return None
    # Richest premium among qualifiers = the assignment-acceptable, trend-supported strike.
    return max(qualifying, key=lambda r: abs(r["delta"]))


# --------------------------------------------------------------------------- #
# FLASH CHECK on one ticker
# --------------------------------------------------------------------------- #
def flash_check(symbol, dte=None):
    gp = load_gp()
    symbol = symbol.upper()
    tp = gp["trade_params"]
    core = set(gp["watchlists"]["core"]); flex = set(gp["watchlists"]["flex"])
    tier_universe = "CORE" if symbol in core else ("FLEX" if symbol in flex else "OTHER")

    q = (mkt.get_quotes([symbol]) or {}).get(symbol)
    price = q.get("price") if q else None
    chg = q.get("change_percent") if q else None

    qqq = cloud_score("QQQ", "daily")
    t_daily = cloud_score(symbol, "daily")
    t_weekly = cloud_score(symbol, "weekly")
    setup = tier_for_move(chg, gp)

    reasons, verdict = [], "TRADE"

    def fail(msg):
        nonlocal verdict
        verdict = "REJECT"; reasons.append(msg)

    # Gate 1: QQQ
    if qqq["score"] is not None and qqq["score"] < 2:
        fail(f"QQQ market gate: {qqq['score']}/3 daily clouds bullish (need >=2) -> risk-off")
    # Gate 2: ticker trend (daily AND weekly >=2/3; weekly senior)
    if t_weekly["score"] is not None and t_weekly["score"] < 2:
        fail(f"{symbol} weekly clouds {t_weekly['score']}/3 (<2) -> weekly trend not bullish")
    if t_daily["score"] is not None and t_daily["score"] < 2:
        fail(f"{symbol} daily clouds {t_daily['score']}/3 (<2)")
    # Gate: universe
    if tier_universe == "OTHER":
        fail(f"{symbol} not on Core/Flex watchlist (needs explicit approval)")
    # Gate: pullback core-only (gameplan.correction_protocol.pullback_core_only)
    if tier_universe == "FLEX" and gp.get("correction_protocol", {}).get("pullback_core_only"):
        try:
            import pullback
            dd = pullback.qqq_drawdown(gp)
            if dd.get("core_only"):
                fail(f"Pullback mode ({dd['bucket']}, QQQ {dd['drawdown_pct']:+.1f}% from high): new entries are Core only")
        except Exception:
            pass
    # Gate: red-day requirement
    intraday = None
    if setup == "NO_TRADE":
        # TACTICAL_INTRADAY override attempt — ONLY for green day, NOT for hard-gate failures
        ip = gp.get("intraday_pullback", {})
        if ip.get("enabled", False):
            # Cash-state eligibility check
            snap = rec.build_snapshot()
            cash_pct = snap["cash_reserve_pct"] * 100
            eligible_states = ip.get("cash_state_eligible", [])
            # Map cash pct to state label
            if cash_pct > 70:
                cash_state = "very cash-heavy"
            elif cash_pct >= 50:
                cash_state = "target/moderate"
            elif cash_pct >= 30:
                cash_state = "aggressively deployed"
            else:
                cash_state = "below hard reserve"

            if cash_state in eligible_states:
                intraday = check_intraday_pullback(symbol, gp)
                if intraday["eligible"]:
                    setup = intraday["grade"]  # override NO_TRADE to TACTICAL_INTRADAY-60m/30m
                    reasons.append(f"OVERRIDE: green day + {intraday['candle_timeframe']} red pullback {intraday['pullback_pct']:.2f}% -> {setup}")
                else:
                    fail(f"{symbol} is {chg:+.1f}% -> green day, intraday override failed: {'; '.join(intraday['reasons'])}")
            else:
                fail(f"{symbol} is {chg:+.1f}% -> green day, intraday mode blocked (cash state: {cash_state})")
        else:
            fail(f"{symbol} is {chg:+.1f}% -> green/inadequate pullback, do not chase")

    candidates, under = rank_strikes(symbol, gp, dte)
    strike = candidates[0] if candidates else None  # best pick = primary ticket
    if strike:
        iv = strike["iv"]
        if iv is not None and iv <= tp["iv_floor_pct"]:
            fail(f"IV {iv:.0f}% <= {tp['iv_floor_pct']}% floor (insufficient premium)")
        elif iv is not None and iv >= tp["iv_danger_pct"]:
            fail(f"IV {iv:.0f}% >= {tp['iv_danger_pct']}% (premium trap)")
    else:
        reasons.append("Could not fetch usable option candidates (verify liquidity manually)")

    # Sizing vs live portfolio
    snap = rec.build_snapshot()
    head = sizing_headroom(symbol, snap, gp)

    # TACTICAL_INTRADAY sizing override: max 5% single entry, single tranche only
    # Also raises ticker combined cap from 20% to 30% for intraday entries
    ip = gp.get("intraday_pullback", {})
    if setup and setup.startswith("TACTICAL_INTRADAY"):
        tactical_cap = ip.get("max_single_entry_pct", 0.05) * snap["combined_net_liq"]
        # Override ticker combined cap for intraday (default 30% vs standard 20%)
        tactical_ticker_cap = ip.get("max_ticker_combined_override_pct", 0.30)
        rules = gp["position_rules"]
        nlv = snap["combined_net_liq"]
        ticker_now = snap["ticker_exposure"].get(symbol, 0.0)
        room_combined_tactical = tactical_ticker_cap * nlv - ticker_now
        single_entry = rules.get("max_single_entry_pct", rules["max_single_ticker_combined_pct"]) * nlv
        # For intraday, allow the tactical cap even with existing positions
        room_combined_tactical = min(room_combined_tactical, single_entry)
        # Recalculate max_collateral with tactical ticker cap
        room_deploy = gp["capital"]["deployed_absolute_max_pct"] * nlv - snap["combined_collateral"]
        room_cash = (snap["cash_reserve_pct"] - gp["capital"]["cash_reserve_floor_pct"]) * nlv
        best_ira_room = head["best_ira_room"]
        head["max_collateral"] = max(0.0, min(room_combined_tactical, room_deploy, room_cash, best_ira_room))
        head["max_collateral"] = min(head["max_collateral"], tactical_cap)
        head["tactical_override"] = True
        head["tactical_cap"] = tactical_cap
        head["tactical_ticker_cap"] = tactical_ticker_cap
        head["room_combined_tactical"] = room_combined_tactical
    else:
        head["tactical_override"] = False

    contracts = 0
    if strike and head["max_collateral"] > 0:
        contracts = int(head["max_collateral"] // (strike["strike"] * 100))
    if contracts < 1:
        fail(f"No sizing room under caps (max collateral ${head['max_collateral']:,.0f})")

    if verdict != "REJECT" and setup in ("B",) and snap["cash_reserve_pct"] <= 0.70:
        verdict = "WATCH"; reasons.append("B setup requires cash > 70%")

    # TACTICAL_INTRADAY: single tranche only, and force 1 contract if strike fits under cap
    if verdict != "REJECT" and setup and setup.startswith("TACTICAL_INTRADAY"):
        if contracts > 1:
            contracts = 1
            reasons.append("TACTICAL_INTRADAY: single tranche only (1 contract)")
        elif contracts < 1 and head["max_collateral"] >= strike["strike"] * 100:
            contracts = 1
            reasons.append("TACTICAL_INTRADAY: single tranche (1 contract, strike fits under 5% cap)")

    if verdict == "TRADE" and (t_daily["status"] != "OK" or t_weekly["status"] != "OK"):
        reasons.append("clouds computed from Schwab data - confirm on TradingView")

    # Strike spectrum + assignment-mode pick (Balanced profile). Best-effort:
    # never let a chain/data hiccup break the core verdict.
    trend_strong = trend_is_strong(t_daily, t_weekly, gp)
    spectrum, spec_exp, spec_under, support = [], None, None, None
    assignment_pick = None
    try:
        spectrum, spec_exp, spec_under, support = strike_spectrum(symbol, gp, dte)
        assignment_pick = pick_assignment_strike(spectrum, trend_strong, gp)
    except Exception as e:
        reasons.append(f"(strike-spectrum unavailable: {e})")

    return {
        "symbol": symbol, "universe": tier_universe, "price": price, "change_pct": chg,
        "setup_tier": setup, "verdict": verdict, "reasons": reasons,
        "qqq": qqq, "daily": t_daily, "weekly": t_weekly,
        "strike": strike, "candidates": candidates, "contracts": contracts, "headroom": head,
        "intraday": intraday,
        "trend_strong": trend_strong, "spectrum": spectrum, "spectrum_exp": spec_exp,
        "support": support, "assignment_pick": assignment_pick,
        "as_of": datetime.now().isoformat(timespec="seconds"),
    }


def render_flash(r):
    gp = load_gp()
    L = []
    L.append("=" * 60)
    L.append(f"FLASH CHECK: {r['symbol']}  ->  {r['verdict']}")
    L.append("=" * 60)
    if r["reasons"]:
        L.append("  " + r["reasons"][0])
    ch = f"{r['change_pct']:+.1f}%" if r["change_pct"] is not None else "n/a"
    L.append(f"  {r['universe']} | ${r['price']} ({ch}) | setup {r['setup_tier']}")
    L.append(f"  QQQ daily {r['qqq'].get('score')}/3 | {r['symbol']} daily "
             f"{r['daily'].get('score')}/3 | weekly {r['weekly'].get('score')}/3 (weekly senior)")
    cands = r.get("candidates") or []
    if cands:
        tp = gp["trade_params"]
        L.append("")
        L.append(f"  TOP {len(cands)} FITTING CSPs (OTM ~{tp['delta_target']:.2f}d, "
                 f"{tp['flash_dte_min']}-{tp['flash_dte_max']} DTE, ranked by capital efficiency ROC/day):")
        L.append("    #  STRIKE   EXP          DTE  DELTA  PREM    ROC    ANN%  SPRD   OI     LIQ")
        for i, c in enumerate(cands, 1):
            dlt = f"{c['delta']:.2f}" if c["delta"] is not None else " n/a"
            sp = f"{c['spread_pct']:.0f}%" if c["spread_pct"] is not None else "n/a"
            oi = c["oi"] if c["oi"] is not None else 0
            liq = "ok" if c.get("liquid") else "THIN"
            mark = "*" if i == 1 else " "
            L.append(f"   {mark}{i} {c['strike']:>6g}P {c['exp']}  {c['dte']:>3}  "
                     f"{dlt:>5}  ${c['premium']:<5} {c['roc']*100:>4.1f}% {c['annual_roc']*100:>4.0f}% "
                     f"{sp:>4}  {oi:>6}  {liq}")
    s = r["strike"]
    h = r["headroom"]
    # Show ticket for TRADE or TACTICAL_INTRADAY (even if WATCH)
    show_ticket = (r["verdict"] == "TRADE" or 
                   (r["setup_tier"] and r["setup_tier"].startswith("TACTICAL_INTRADAY")))
    if show_ticket and s and r["contracts"] >= 1:
        collat = s["strike"] * 100 * r["contracts"]
        credit = s["premium"] * 100 * r["contracts"]
        L.append("")
        L.append("  TICKET - best pick #1 (you place it):")
        L.append(f"    SELL TO OPEN  {r['contracts']}x {r['symbol']} {s['strike']:g} PUT  {s['exp']}")
        L.append(f"    LIMIT ~${s['premium']:.2f} (start mid) | IRA *{h['best_ira']}")
        L.append(f"    Collateral ${collat:,.0f} | credit ~${credit:,.0f}")
        L.append(f"    Then: BUY TO CLOSE GTC @ ${s['premium']*0.5:.2f} (50%)")
        L.append(f"    Max contracts under caps: {r['contracts']} (room ${h['max_collateral']:,.0f})")
        if h.get("tactical_override"):
            L.append(f"    TACTICAL_INTRADAY cap: ${h['tactical_cap']:,.0f} (5% max)")
    # Intraday override details
    intra = r.get("intraday")
    if intra and intra.get("eligible"):
        L.append("")
        L.append(f"  INTRADAY OVERRIDE DETAILS:")
        L.append(f"    Session high: ${intra['session_high']:.2f}")
        L.append(f"    Pullback: {intra['pullback_pct']:.2f}%")
        L.append(f"    Candle: {intra['candle_timeframe']} (completed)")

    # --- Strike spectrum: income -> assignment, annotated vs support --------- #
    spec = r.get("spectrum") or []
    if spec:
        sup = r.get("support") or {}
        sl = f"${sup['swing_low']:.2f}" if sup.get("swing_low") else "n/a"
        e50 = f"${sup['ema50']:.2f}" if sup.get("ema50") else "n/a"
        L.append("")
        L.append(f"  STRIKE SPECTRUM  exp {r.get('spectrum_exp')}  "
                 f"(support: 20d low {sl} | 50EMA {e50})")
        L.append("    DELTA  STRIKE   PREM    ROC   ANN%  IF-ASSIGNED  VS SUPPORT")
        for c in spec:
            dl = f"{abs(c['delta']):.2f}" if c["delta"] is not None else " n/a"
            L.append(f"    {dl:>5}  {c['strike']:>6g}P  ${c['premium']:<5} "
                     f"{c['roc']*100:>4.1f}% {c['annual_roc']*100:>4.0f}%  "
                     f"${c['assign_basis']:<9} {c['support']}")
        ap = r.get("assignment_pick")
        if ap:
            L.append("")
            L.append("  ASSIGNMENT-MODE PICK (strong trend + strike at/below support):")
            L.append(f"    SELL TO OPEN {r['symbol']} {ap['strike']:g} PUT  {r.get('spectrum_exp')}  "
                     f"(~{abs(ap['delta']):.2f}d)")
            L.append(f"    Premium ~${ap['premium']:.2f} | ROC {ap['roc']*100:.1f}% | "
                     f"if assigned you own at ${ap['assign_basis']:.2f} ({ap['support']})")
            L.append("    Higher premium AND a good entry if assigned. Size within your caps.")
        elif r.get("trend_strong"):
            L.append("  Assignment mode: no strike sits at/below support right now -> "
                     "take income delta, don't reach.")
        else:
            L.append("  Assignment mode: trend not strong enough (needs daily+weekly >=2/3) "
                     "-> income only.")

    L.append("")
    L.append("  Advisory only - not investment advice. You have the final say.")
    L.append("=" * 60)
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# Premarket / watchlist scan (the 7 AM MST routine)
# --------------------------------------------------------------------------- #
def _telegram_send(text):
    """Ping the user's Telegram. Reads git-ignored telegram_config.json."""
    cfgf = CONFIG_DIR / "telegram_config.json"
    if not cfgf.exists():
        print("[telegram] no telegram_config.json - skipping alert")
        return False
    import urllib.parse, urllib.request
    cfg = json.load(open(cfgf))
    tok, chat = cfg.get("bot_token"), cfg.get("chat_id")
    if not tok or not chat:
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data)
    try:
        urllib.request.urlopen(req, context=mkt.get_ssl_context(), timeout=15).read()
        print("[telegram] alert sent")
        return True
    except Exception as e:
        print(f"[telegram] send failed: {e} (has the user sent /start to the bot?)")
        return False


def scan(min_pct=-3.0, notify=False, tickers=None):
    gp = load_gp()
    tickers = tickers or (gp["watchlists"]["core"] + gp["watchlists"]["flex"])
    quotes = mkt.get_quotes(tickers) or {}
    # Health check: no quotes at all => likely Schwab auth lapsed (refresh token
    # expires ~7 days). Surface it instead of silently reporting "no candidates".
    if not quotes:
        msg = ("Aristotle scan could NOT reach Schwab (no quotes). Likely re-auth "
               "needed: run schwab_auth_manual.py then finish_auth.py.")
        print("[health] " + msg)
        if notify:
            _telegram_send(msg)
        return []
    rows = []
    for t in tickers:
        q = quotes.get(t)
        if not q or q.get("change_percent") is None:
            continue
        chg = q["change_percent"]
        if chg <= min_pct:
            rows.append((t, q["price"], chg, tier_for_move(chg, gp)))
    rows.sort(key=lambda x: x[2])
    print("=" * 56)
    print(f"PREMARKET FLYWHEEL SCAN  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  down-day candidates (<= {min_pct:g}%)")
    print("=" * 56)
    if not rows:
        print("  No qualifying pullbacks. Cash is a position - wait.")
    for t, px, chg, tier in rows:
        universe = "CORE" if t in gp["watchlists"]["core"] else "FLEX"
        print(f"  {tier:<4} {universe:<4} {t:<5} ${px:<8} {chg:+.1f}%   -> flash_check {t}")
    print("=" * 56)
    print("Trigger only - each candidate still must pass every gate. You decide.")

    # Telegram alert only when there is something to act on (silent otherwise).
    if notify and rows:
        lines = ["Aristotle premarket flywheel scan - down-day candidates:"]
        for t, px, chg, tier in rows:
            lines.append(f"  {tier}  {t}  ${px}  {chg:+.1f}%")
        lines.append("")
        lines.append("Trigger only - each still must pass every gate. Ask Aristotle to FLASH CHECK.")
        _telegram_send("\n".join(lines))
    return rows


def layer_scan(notify=False, tickers=None):
    """Add-a-tranche radar. Surfaces qualified UPTREND names that still have
    single-ticker headroom, where either a smaller pullback (>= layering min) OR
    a hold of the cloud justifies layering in another entry. The point: deploy
    idle cash into setups that ALREADY qualify, more frequently -- never force."""
    gp = load_gp()
    lay = gp.get("aggression_profile", {}).get("layering", {})
    min_pb = lay.get("min_pullback_pct", -1.5)
    tickers = tickers or (gp["watchlists"]["core"] + gp["watchlists"]["flex"])
    quotes = mkt.get_quotes(tickers) or {}
    if not quotes:
        msg = ("Aristotle layer-scan could NOT reach Schwab (no quotes). Re-auth "
               "likely needed: run schwab_auth_manual.py then finish_auth.py.")
        print("[health] " + msg)
        if notify:
            _telegram_send(msg)
        return []
    snap = rec.build_snapshot()
    nlv = snap["combined_net_liq"] or 0.0
    single_entry = gp["position_rules"].get("max_single_entry_pct", 0.10) * nlv

    rows = []
    for t in tickers:
        q = quotes.get(t)
        if not q or q.get("change_percent") is None:
            continue
        chg = q["change_percent"]
        daily = cloud_score(t, "daily")
        weekly = cloud_score(t, "weekly")
        if not trend_is_strong(daily, weekly, gp):
            continue                                    # only layer into strong trends
        head = sizing_headroom(t, snap, gp)
        room = min(head["max_collateral"], single_entry)
        if room < 100:
            continue                                    # no meaningful headroom left
        pullback_ok = chg <= min_pb
        # Cloud-hold qualifies only on a flat/mild day -- never chase a green spike.
        cloud_hold = (lay.get("cloud_hold_qualifies", True)
                      and daily.get("score", 0) >= 2 and chg <= 1.0)
        if not (pullback_ok or cloud_hold):
            continue
        px = q["price"]
        approx_strike = px * 0.95                        # rough ~0.28d OTM level
        approx_ct = int(room // (approx_strike * 100)) if approx_strike else 0
        rows.append({
            "ticker": t, "price": px, "chg": chg,
            "held_pct": (head["ticker_now"] / nlv * 100) if nlv else 0.0,
            "room": room, "approx_ct": approx_ct,
            "reason": "pullback" if pullback_ok else "cloud hold",
            "daily": daily.get("score"), "weekly": weekly.get("score"),
        })
    rows.sort(key=lambda r: r["chg"])                   # biggest dips first

    print("=" * 60)
    print(f"LAYERING RADAR (add-a-tranche)  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  strong-trend names with headroom | layer trigger: <= {min_pb:g}% OR cloud hold")
    print("=" * 60)
    if not rows:
        print("  Nothing qualifies to layer right now. Cash is a position.")
    else:
        print("  TICKER  PRICE     CHG    HELD   ADD-ROOM    ~CT  TRIGGER   D/W")
        for r in rows:
            print(f"  {r['ticker']:<6} ${r['price']:<8} {r['chg']:+5.1f}% "
                  f"{r['held_pct']:>4.1f}%  ${r['room']:>8,.0f}  {r['approx_ct']:>3}  "
                  f"{r['reason']:<9} {r['daily']}/{r['weekly']}")
        print("")
        print("  Each is a qualified place to add a tranche (single entry <= 10%).")
        print("  Run  flash_check <TICKER>  for the exact strike + ticket. You decide.")
    print("=" * 60)

    if notify and rows:
        lines = ["Aristotle LAYERING RADAR - qualified add-a-tranche names:"]
        for r in rows:
            lines.append(f"  {r['ticker']}  ${r['price']}  {r['chg']:+.1f}%  "
                         f"room ${r['room']:,.0f} (~{r['approx_ct']} ct)  [{r['reason']}]")
        lines.append("")
        lines.append("FLASH CHECK any name for the exact strike. You place every order.")
        _telegram_send("\n".join(lines))
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Aristotle FLASH CHECK")
    ap.add_argument("ticker", nargs="?", help="ticker to evaluate")
    ap.add_argument("--dte", type=int, default=None)
    ap.add_argument("--scan", action="store_true", help="premarket watchlist scan")
    ap.add_argument("--layer", action="store_true", help="add-a-tranche layering radar")
    ap.add_argument("--min", type=float, default=-3.0, help="scan: min %% down (e.g. -5)")
    ap.add_argument("--notify", action="store_true", help="send Telegram alert if candidates found")
    ap.add_argument("--tickers", help="scan: custom comma-separated tickers instead of the watchlist")
    args = ap.parse_args()

    custom = [t.strip().upper() for t in args.tickers.split(",")] if args.tickers else None
    if args.layer:
        layer_scan(notify=args.notify, tickers=custom)
    elif args.scan:
        scan(args.min, notify=args.notify, tickers=custom)
    elif args.ticker:
        print(render_flash(flash_check(args.ticker, args.dte)))
    else:
        ap.print_help()
