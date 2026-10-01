"""trend_watch.py - watch tickers' weekly cloud and Telegram-alert on a flip
================================================================================
For names that are REJECTED only because their weekly trend hasn't confirmed yet
(e.g. ETHU at weekly 1/3). Checks each watched ticker's weekly cloud once a day
and pings Telegram the moment it crosses UP to >=2 (re-qualifies for the trend
gate) -- so you stop hand-checking and let the signal come to you.

Pure Python, zero LLM tokens. State lives in trend_watch.json. Run daily after
the close via Windows Task "Aristotle Trend Watch".

Add a ticker:    python trend_watch.py --add ETHU
Remove:          python trend_watch.py --remove ETHU
List / check now: python trend_watch.py
"""
import argparse
import json
import pathlib
from datetime import datetime

import flash_check as fc

HERE = pathlib.Path(__file__).parent
WATCH = HERE / "trend_watch.json"


def load():
    if WATCH.exists():
        return json.loads(WATCH.read_text(encoding="utf-8"))
    return {}


def save(d):
    WATCH.write_text(json.dumps(d, indent=2), encoding="utf-8")


def check(notify=True):
    watch = load()
    if not watch:
        print("[trend_watch] watch list is empty (add one: python trend_watch.py --add ETHU)")
        return
    changed = False
    for tkr, cfg in watch.items():
        wk = fc.cloud_score(tkr, "weekly")
        dl = fc.cloud_score(tkr, "daily")
        cur = wk.get("score")
        if cur is None:
            print(f"[trend_watch] {tkr}: weekly score unavailable ({wk.get('status')})")
            continue
        prev = cfg.get("last_weekly_score")
        flipped_up = prev is not None and prev < 2 and cur >= 2
        if flipped_up:
            msg = (f"Aristotle trend-watch: {tkr} WEEKLY cloud flipped to {cur}/3 "
                   f"(was {prev}/3) -> it now CLEARS your weekly trend gate. "
                   f"Daily {dl.get('score')}/3. Run FLASH CHECK {tkr} to see if it's a "
                   f"qualified setup now.")
            print(f"[trend_watch] *** ALERT: {tkr} weekly {prev}->{cur} ***")
            if notify:
                fc._telegram_send(msg)
        else:
            print(f"[trend_watch] {tkr}: weekly {cur}/3 (prev {prev}) daily {dl.get('score')}/3 - no flip")
        if cur != prev:
            cfg["last_weekly_score"] = cur
            cfg["last_checked"] = datetime.now().isoformat(timespec="seconds")
            changed = True
    if changed:
        save(watch)


def add(tkr):
    tkr = tkr.upper()
    watch = load()
    wk = fc.cloud_score(tkr, "weekly")
    watch[tkr] = {
        "last_weekly_score": wk.get("score"),
        "added": datetime.now().isoformat(timespec="seconds"),
        "note": f"Watching for weekly >=2 to re-qualify for CSPs. Baseline weekly {wk.get('score')}/3.",
    }
    save(watch)
    print(f"[trend_watch] now watching {tkr} (baseline weekly {wk.get('score')}/3). "
          f"You'll be pinged when it flips to >=2.")


def remove(tkr):
    tkr = tkr.upper()
    watch = load()
    if tkr in watch:
        del watch[tkr]
        save(watch)
        print(f"[trend_watch] removed {tkr}")
    else:
        print(f"[trend_watch] {tkr} was not on the watch list")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Aristotle weekly-cloud trend watch")
    ap.add_argument("--add", help="add a ticker to the watch list")
    ap.add_argument("--remove", help="remove a ticker")
    ap.add_argument("--quiet", action="store_true", help="check but do not send Telegram")
    args = ap.parse_args()
    if args.add:
        add(args.add)
    elif args.remove:
        remove(args.remove)
    else:
        check(notify=not args.quiet)
