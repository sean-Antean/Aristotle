"""
profit_watch.py - Telegram alert when an open short option nears an early-profit level
=====================================================================================
For "take early profits" decisions: checks every open short option and pings
Telegram the first time its profit (at the bid/ask midpoint) reaches each level
in --levels (default 30% = approaching, 35% = there). One ping per position per
level; resets if the position closes and reopens.

Read-only: places nothing. Pure Python, zero LLM tokens. Stops itself after
--until (so a week's watch can't keep pinging forever).

    python profit_watch.py                     # check now, alert if crossed
    python profit_watch.py --dry               # check now, never send
    python profit_watch.py --until 2026-10-09 --levels 0.30,0.35
"""
import argparse
import json
import pathlib
from datetime import date, datetime

import flash_check as fc
import reconcile as rec
import schwab_bridge as mkt

HERE = pathlib.Path(__file__).parent
STATE = HERE / "profit_watch_state.json"


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", default="0.30,0.35")
    ap.add_argument("--until", default="2026-10-09", help="last day to run (YYYY-MM-DD)")
    ap.add_argument("--dry", action="store_true", help="print only, never send Telegram")
    a = ap.parse_args()

    if date.today() > date.fromisoformat(a.until):
        print(f"[profit_watch] past --until {a.until}; nothing to do")
        return
    levels = sorted(float(x) for x in a.levels.split(","))

    snap = rec.build_snapshot()
    opts = [o for o in snap["open_options"] if o.get("entry_premium")]
    quotes = mkt.get_quotes([o["symbol"] for o in opts]) or {}
    state, seen = load_state(), set()
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    for o in opts:
        q = quotes.get(o["symbol"], {})
        bid, ask = q.get("bid"), q.get("ask")
        if bid is None or ask is None:
            print(f"[profit_watch] {o['symbol']}: no quote")
            continue
        entry, mid = o["entry_premium"], (bid + ask) / 2
        prof_mid, prof_ask = 1 - mid / entry, 1 - ask / entry
        key = o["symbol"]
        seen.add(key)
        done = state.setdefault(key, [])
        print(f"[profit_watch] {stamp} {key.strip():24} x{o['contracts']:.0f} entry {entry:.2f} "
              f"bid/ask {bid:.2f}/{ask:.2f}  profit mid {prof_mid:+.0%} (at ask {prof_ask:+.0%})")
        hit = [lv for lv in levels if prof_mid >= lv and lv not in done]
        if not hit:
            continue
        lv = max(hit)
        dollars = (entry - mid) * 100 * o["contracts"]
        msg = (f"Aristotle profit-watch: {o['underlying']} {o['strike']:g}{o['type'][0]} "
               f"{o['expiry']} x{o['contracts']:.0f} is at {prof_mid:.0%} profit "
               f"(~${dollars:,.0f} at mid {mid:.2f}; {prof_ask:.0%} if you pay the ask {ask:.2f}). "
               f"Early-profit level {lv:.0%} reached - decide whether to close. Nothing was placed.")
        print(f"[profit_watch] *** ALERT {key.strip()} >= {lv:.0%} ***")
        if not a.dry and fc._telegram_send(msg):
            done.extend(x for x in hit if x not in done)

    for k in list(state):
        if k not in seen:
            del state[k]  # position closed: re-arm if it ever reopens
    if not a.dry:
        STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
