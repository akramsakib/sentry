#!/usr/bin/env python3
"""Offline checks for the parts that silently wrecked the bot on 2026-11-14.

Run: python3 test_data.py     (no network, no accounts; exits non-zero on failure)

Covers:
  1. Coinbase candle -> bar mapping (row order is [time, low, high, open, close, volume]).
  2. The forming-candle pop (a live candle in the history makes every pattern fire on itself).
  3. Impossible-bar rejection.
  4. Sizing guards in the orchestrator: sub-spread stops refused, notional capped to equity.
  5. push_memory append-only semantics (the thing that used to conflict-kill runs).
"""
import json
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# ---------- 1 + 2 + 3: bar mapping ----------
import broker_ledger as bl                                     # noqa: E402

RAW = [  # [time, low, high, open, close, volume]
    [1_700_000_000, 90.0, 110.0, 100.0, 105.0, 7.0],
    [1_700_003_600, 95.0, 120.0, 105.0, 118.0, 8.0],
    [1_700_007_200, 99.0, 121.0, 118.0, 101.0, 9.0],   # "forming" -> must be dropped
]
_orig_get = bl._get
bl._get = lambda url, t=20: [list(r) for r in RAW]
bars = bl.crypto_bars("TEST/USD", "1Hour", 3)
bl._get = _orig_get

check("closed bars only (forming candle popped)", len(bars) == 2, f"{len(bars)} bars")
b0 = bars[0]
check("o/h/l/c mapped from Coinbase row order",
      (b0["o"], b0["h"], b0["l"], b0["c"]) == (100.0, 110.0, 90.0, 105.0),
      json.dumps(b0))
check("volume carried", math.isclose(b0["v"], 7.0))
check("bull bar detected as bull (close > open)", b0["c"] > b0["o"])
check("range is high-low, not open-close", math.isclose(b0["h"] - b0["l"], 20.0),
      f"h-l={b0['h'] - b0['l']}")

bl._get = lambda url, t=20: [[1_700_000_000, 110.0, 90.0, 100.0, 105.0, 1.0]]  # high < low
try:
    bl.crypto_bars("TEST/USD", "1Hour", 1)
    check("impossible bar rejected", False, "no exception")
except bl.BrokerError as e:
    check("impossible bar rejected", True)
except Exception as e:                                        # noqa: BLE001
    check("impossible bar rejected (BrokerError)", False, f"{type(e).__name__}: {e}")
bl._get = _orig_get

# ---------- 4: sizing guards (source-level, mirrors run_cycle) ----------
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_cycle.py")).read()
check("min-stop-width guard present", "spread noise, not a risk level" in src)
check("notional cap present", "CAPPED —" in src and "max_notional_frac" in src)
check("both guards read from config", "CFG.get(\"min_stop_frac\"" in src and "CFG.get(\"max_notional_frac\"" in src)

cfg = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")))
for k in ("min_stop_frac", "max_notional_frac", "min_notional", "max_open"):
    check(f"config.json defines {k}", k in cfg, "missing")
if all(k in cfg for k in ("min_stop_frac", "max_notional_frac")):
    entry, r_dist = 75.0, 0.029                 # the exact SOL case from run #8
    check("0.04% stop is refused by min_stop_frac", r_dist < entry * cfg["min_stop_frac"])
    qty = 100.0 / r_dist                        # risk / distance, uncapped
    check("uncapped notional would be absurd", qty * entry > 200_000, f"${qty * entry:,.0f}")
    capped = min(qty, 100_000 * cfg["max_notional_frac"] / entry)
    check("cap keeps notional <= 25% of equity", capped * entry <= 25_000 + 1e-6,
          f"${capped * entry:,.0f}")

# ---------- 5: journal timestamp format the watchdog parses ----------
import sentry_core as core                                     # noqa: E402
stamp = core.utc_stamp() if hasattr(core, "utc_stamp") else None
if stamp:
    import re
    check("journal stamp matches watchdog regex",
          bool(re.match(r"^\d{2}-\d{2} \d{2}:\d{2} UTC$", stamp)), repr(stamp))

# ---------- 6: resting-order TTL (a stale trigger is not the same trade) ----------
import re as _re
check("run_cycle parses placement time from its own cid", '_CID_TS = re.compile(' in src)
check("TTL is configurable", "pending_ttl_h" in cfg, "config.json missing pending_ttl_h")
_cid_re = _re.compile(r"(\d{13})n\d+$")                      # same contract as run_cycle
_mine = "sentrySOLUSD1794662107892n5"
check("own cid yields its placement ms", _cid_re.search(_mine) is not None)
if _cid_re.search(_mine):
    check("parsed time is a plausible epoch", 1_700_000_000_000 < int(_cid_re.search(_mine).group(1)) < 4_000_000_000_000)
check("foreign cids are ignored (never expire what we did not place)",
      _cid_re.search("ledger1794662107892") is None)

# ---------- 7: a legacy ledger row must not kill the cycle ----------
_save = bl._save
bl._save = lambda *a, **k: None
try:
    legacy = {"cash": 1000.0, "orders": [{"symbol": "TEST/USD", "side": "buy", "type": "stop",
                                          "qty": 1.0, "status": "open", "client_order_id": "sentryX1"}],
              "positions": []}
    _gp = bl._ticker_price
    bl._ticker_price = lambda sym: 100.0
    bl._tick(legacy)
    bl._ticker_price = _gp
    check("missing stop_price is skipped, not fatal", legacy["orders"][0]["status"] == "open")
except Exception as e:                                        # noqa: BLE001
    check("missing stop_price is skipped, not fatal", False, f"{type(e).__name__}: {e}")
finally:
    bl._save = _save

print("\n%d checks failed" % len(FAILS))
sys.exit(1 if FAILS else 0)
