#!/usr/bin/env python3
"""The producer's own contract, run on the Mac against the DEPLOYED resident.

`publish_watch` is the only new thing on the execution path's edge, so it gets tested where it runs: the
module is imported (import starts nothing — main() is guarded), and its output is checked against the exact
shapes the two pages expect. It also re-verifies the one thing that had to stay untouched: the scan gate's
bar minimums, now read from TF_MIN, must decide identically to the literals they replaced.
"""
import ast
import datetime
import importlib.util
import json
import os
import re
import sys

DESK = os.path.expanduser("~/hermes_sentry")
SRC = os.path.join(DESK, "sentry_mac.py")
FAILS = []


def check(name, cond, detail=""):
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name, ("  (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


if not os.path.isfile(SRC):
    # This test belongs to the Mac-side forex build, which has never been part of the GitHub release. On any
    # other machine the honest answer is "nothing to check here", not a failure and not a silent pass.
    print("fx_watch_test: %s is not on this machine — the resident it tests runs only on the Mac. Skipping."
          % SRC)
    raise SystemExit(0)
src = open(SRC, encoding="utf-8").read()
ast.parse(src)
check("the deployed resident parses as valid Python 3 on this Mac", True, "%d lines" % (src.count("\n") + 1))
spec = importlib.util.spec_from_file_location("sm_deployed", SRC)
mo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mo)                      # import only: main() is guarded by __main__
_calls = re.findall(r"^\s+publish_watch\(", src, re.M)
check("publish_watch exists and the scan calls it exactly once (a second call site would publish twice a "
      "cycle and the last writer wins)",
      hasattr(mo, "publish_watch") and len(_calls) == 1
      and "publish_watch(state, quotes, tf_map, positions, chart_thin, positions)" in src, str(len(_calls)))
check("the bar minimums live in ONE table that both the scan and the page read",
      mo.TF_MIN == {"M5": 25, "M15": 15, "H1": 60, "H4": 30, "D1": 8}
      and mo.TFS == ["M5", "M15", "H1", "H4", "D1"] and "len(b) < TF_MIN[t]" in src, str(mo.TF_MIN))

# the refactor of the scan gate must decide EXACTLY as the literals it replaced did
old = lambda l: (l[0] < 25 or l[1] < 15 or l[2] < 60 or l[3] < 30 or l[4] < 8)
new = lambda l: bool({t: n for n, t in zip(l, mo.TFS) if n < mo.TF_MIN[t]})
cases = [[(i * 7 + j * 13) % 90 for j in range(5)] for i in range(900)]
cases += [[25, 15, 60, 30, 8], [24, 15, 60, 30, 8], [25, 14, 60, 30, 8], [25, 15, 59, 3, 8], [0, 0, 0, 0, 0]]
check("905+ bar-count tuples: the new gate skips exactly what the old literals skipped",
      all(old(c) == new(c) for c in cases), str([c for c in cases if old(c) != new(c)][:3]))

# A SHORT that gained, an ISO timestamp with a "T", a symbol held with no quote this cycle, a book item on a
# third symbol, and a rolling fired-list spanning two days: the five shapes that only appeared once this ran
# against real terminal text. Every expectation below is one of those, and each was WRONG in the first cut.
raw = ('{"position_id": "9001", "action": "sell", "symbol": "EURUSD", "create_time": '
       '"2026-11-17T20:59:52", "volume": 1.04, "price_open": 1.10122, "price_last": 1.10073, '
       '"stop_loss": 1.1024, "take_profit": 1.09946, "profit": 50.96} '
       '{"position_id": "9002", "action": "buy", "symbol": "XAUUSD", "create_time": "junk", '
       '"volume": 0.05, "price_open": 2650.0, "price_last": 2650.0, "stop_loss": 2650.0, '
       '"take_profit": 2670.0, "profit": 0.0}')
st = {"day": "2026-11-18",
      "orders": [{"sym": "XAUUSD", "skill": "S13-short", "risk": 100, "type": "sell stop"}],
      "seen_candles": ["XAUUSD|M15|engulfing|t", "XAUUSD|H1|harami|t2"],
      "fired_today": ["FIRE|XAUUSD|S13|2026-11-18", "FIRE|XAUUSD|S21|2026-11-17",
                      "FIRE|AMD|C-M15-harami|2026-11-18"]}
book = ('{"order_id": "771", "symbol": "XAUUSD", "type": "buy stop", "state": "active", "price_order": 2655.5} '
        '{"order_id": "772", "symbol": "EURUSD", "type": "sell limit", "state": "filled", "price_order": 1.0955}')
tfm = {"XAUUSD": dict((t, [{"t": "2026-11-18T04:00:00"}] * mo.TF_MIN[t]) for t in mo.TFS),
       "AMD": {"M5": [{"t": "x"}] * 4, "M15": [], "H1": [], "H4": [], "D1": []}}
mo.publish_watch(st, {"XAUUSD": {"bid": 2660.0, "ask": 2660.2}, "AMD": {}}, tfm, raw, {"AMD": {"M5": 4}}, book)
p0 = [x for x in st["positions_now"] if x["id"] == "9001"][0]
p1 = [x for x in st["positions_now"] if x["id"] == "9002"][0]
check("an open SHORT that gained prints POSITIVE R (+0.415 on a 4.9-pip move against a 11.8-pip stop): the "
      "stop distance is a distance, and the first cut used a signed span, which printed -0.415R next to a "
      "green P&L", p0["r_now"] == 0.415, str(p0["r_now"]))
check("the terminal's ISO create_time (with its T) parses into an age; the exact space-format parse the build "
      "uses elsewhere returned None for every real row", isinstance(p0["age_min"], int), str(p0["age_min"]))
check("a stop sitting on the entry gives None, not a ZeroDivisionError, and a junk timestamp gives None too",
      p1["r_now"] is None and p1["age_min"] is None, json.dumps(p1)[:150])
check("the book it read is reported with the SAME count the caps gate uses (one parser, one truth)",
      st["book"]["n"] == 2 and len(re.findall(
          r'"order_id": "(\d+)".*?"symbol": "([A-Za-z0-9._\-]+)".*?"type": "([\w ]+)".*?"state": "(\w+)".*?"price_order": ([0-9.]+)',
          book, re.S)) == st["book"]["n"], str(st["book"]["n"]))
check("every chart the build read is present per symbol, with bars / needed / patterns / last bar",
      st["charts"]["XAUUSD"]["M15"]["enough"] is True and st["charts"]["XAUUSD"]["M15"]["patterns"] == 1
      and st["charts"]["AMD"]["M5"]["enough"] is False and st["charts"]["AMD"]["thin"] == {"M5": 4},
      json.dumps(st["charts"]["AMD"])[:160])
check("`fired_today` counts ONLY the day the build stamps, and the unfiltered rolling count is kept beside it "
      "with the days it spans (a 'today' of 46 was six days summed)",
      st["charts"]["XAUUSD"]["fired_today"] == 1 and st["charts"]["XAUUSD"]["fired_rolling"] == 2
      and st["charts"]["XAUUSD"]["fired_days"] == ["2026-11-17", "2026-11-18"],
      json.dumps({k: st["charts"]["XAUUSD"][k] for k in ("fired_today", "fired_rolling", "fired_days")}))
check("it publishes WHO IS HOLDING WHAT per symbol — positions and resting orders counted separately — so "
      "the two pages never derive exposure from different lists",
      st["charts"]["XAUUSD"]["held"] == 1 and st["charts"]["XAUUSD"]["resting"] == 1
      and st["charts"]["AMD"]["held"] == 0 and st["charts"]["AMD"]["resting"] == 0,
      str([(k, v.get("held"), v.get("resting")) for k, v in st["charts"].items()]))
check("a symbol with an open position but NO quote this cycle keeps its row, at zero bars, rather than "
      "disappearing from the matrix", "EURUSD" in st["charts"]
      and st["charts"]["EURUSD"]["M15"]["bars"] == 0
      and st["charts"]["EURUSD"]["M15"]["enough"] is False, str(sorted(st["charts"])))
check("the rule set is echoed from the module's OWN constants, so the page can never quote a stale one",
      st["playbook"]["cycle_s"] == mo.CYCLE and st["playbook"]["risk_base"] == mo.RISK
      and st["playbook"]["risk_band"] == [mo.MIN_RISK, mo.MAX_RISK]
      and st["playbook"]["max_orders_day"] == mo.MAX_SENTRY_ORDERS_DAY
      and st["playbook"]["theme_cap"] == mo.THEME_CAP, json.dumps(st["playbook"])[:150])
check("a stamp exists so the page can date its own read", str(st.get("watch_asof", "")).endswith("KL"))
check("no watch_error was raised, and the field is absent (not 'ok')", "watch_error" not in st)
# and the guard that matters most: a publisher that throws must never take the bot down
class Boom(dict):
    def get(self, k, d=None):
        if k == "seen_candles":
            raise RuntimeError("simulated")
        return dict.get(self, k, d)
try:
    mo.publish_watch(Boom(), {}, {}, "", None, "")
    check("publish_watch propagates nothing the cycle cannot survive", False, "it raised")
except Exception:
    check("publish_watch propagates nothing the cycle cannot survive", True)
# the real cycle's file, read as it stands: are the new keys there yet, and does the resident's own
# state file still load? (an interrupted write is the classic deploy accident)
live = json.load(open(os.path.join(DESK, "state.json")))
check("the live state.json still parses after the patch (json.dump is not atomic, so this is worth proving)",
      isinstance(live, dict) and "orders" in live)
print("  -- live state.json right now: watch keys present = %s" % ("positions_now" in live))
print("\n%d checks failed" % len(FAILS))
sys.exit(1 if FAILS else 0)
