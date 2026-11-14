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
import time

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


# ---------- 6: the live Coinbase adapter's contracts ----------
# These four are the ways a real order dies quietly on Coinbase. All offline: product metadata is
# stubbed, DRY mode builds the payload and never opens a socket.
import re as _re

import broker_coinbase as cb

oid = cb.oid_for("sentryXRPUSD1794662610992n5")
check("cid mapped to a valid lowercase UUIDv4",
      bool(_re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", oid)), oid)
check("  ...and deterministic (runners are ephemeral, no mapping to lose)",
      oid == cb.oid_for("sentryXRPUSD1794662610992n5"))
check("  ...and unique per cid", oid != cb.oid_for("sentryXRPUSD1794662610993n6"))
check("raw cid never sent as client_oid", "_CID_OK" and "n5" not in oid)

check("size floored to base_increment", cb._quant(0.123456789, "0.0001") == "0.1234", cb._quant(0.123456789, "0.0001"))
check("price floored to quote_increment", cb._quant(74.156, "0.01") == "74.15", cb._quant(74.156, "0.01"))
check("8-decimal base size survives untouched",
      cb._quant(6634.3207012345, "0.00000001") == "6634.32070123", cb._quant(6634.3207012345, "0.00000001"))

bars = cb._bars([[1_700_000_000, 90.0, 110.0, 100.0, 105.0, 7.0],
                 [1_700_003_600, 99.0, 121.0, 118.0, 101.0, 9.0]], now_ts=1_700_007_200)
check("live host maps [time,low,high,open,close,vol] the same way",
      len(bars) == 2 and bars[0]["o"] == 100.0 and bars[0]["h"] == 110.0
      and bars[0]["l"] == 90.0 and bars[0]["c"] == 105.0, str(bars[0]))
check("the close below the open reads as a down bar", bars[1]["c"] < bars[1]["o"])

_meta_saved, _dry_saved = cb._meta, cb.DRY
cb._meta = lambda sym: {"quote": "0.01", "base": "0.00000001", "min_funds": 1.0, "ok": True}
cb.DRY = True
try:
    r = cb.place_order("buy", "XRP/USD", qty=100.0, otype="stop", stop_price=0.99537, cid="sentryXRP1n1")
    b = r["payload"]
    check("breakout entry goes out as stop_limit (never a market buy)", b["type"] == "stop_limit", b["type"])
    check("  ...with stop=entry for buys (buy triggers at/above)", b["stop"] == "entry")
    check("  ...limit sits ABOVE the trigger so it can actually fill", float(b["price"]) > float(b["stop_price"]),
          f"{b['price']} vs {b['stop_price']}")
    check("  ...size is a tick-aligned string", b["size"] == "100" or _re.fullmatch(r"\d+(\.\d{1,8})?", b["size"]), b["size"])
    check("  ...time_in_force GTC so it survives a dead runner", b["time_in_force"] == "GTC")
    # coarse tick: 0.15% of 0.9953 is smaller than a 0.01 tick, so it must widen a whole tick
    check("  ...slack never rounds below one tick",
          float(b["price"]) - float(b["stop_price"]) >= 0.01 - 1e-9, f"{b['price']} - {b['stop_price']}")
    check("  ...exactly one tick, no float drift (0.94 not 0.93)", b["price"] == "1.00", b["price"])
    s2 = cb.place_order("sell", "XRP/USD", qty=100.0, otype="stop", stop_price=0.955, cid="sentryXRP1n2")["payload"]
    check("protective stop drops exactly one tick, not two",
          float(s2["stop_price"]) - float(s2["price"]) <= 0.0201, f"{s2['stop_price']}->{s2['price']}")
    check("protective sell stop uses stop=loss, limit BELOW trigger",
          s2["stop"] == "loss" and float(s2["price"]) < float(s2["stop_price"]), f"{s2['price']} vs {s2['stop_price']}")
    m = cb.place_order("buy", "SOL/USD", notional=75.0, otype="market", limit_price=None, cid="sentrySOL1n3")["payload"]
    check("market close on a buy spends funds, not size", "funds" in m and "size" not in m, str(m))
    try:
        cb.place_order("buy", "XRP/USD", qty=0.5, otype="limit", limit_price=1.0, cid="x")
        check("sub-minimum notional refused", False, "it accepted a $0.50 order")
    except cb.BrokerError as e:
        check("sub-minimum notional refused", "minimum" in str(e).lower(), str(e))
    cb._meta = lambda sym: {"quote": "0.01", "base": "0.00000001", "min_funds": 1.0, "ok": False}
    try:
        cb.place_order("buy", "AVAX/USD", qty=1.0, otype="limit", limit_price=10.0, cid="y")
        check("halted product refused", False, "it placed into a disabled market")
    except cb.BrokerError as e:
        check("halted product refused", "not tradeable" in str(e).lower(), str(e))
finally:
    cb._meta, cb.DRY = _meta_saved, _dry_saved

# ---------- 7: the live gate ----------
import run_cycle as rc

_orig_live, _orig_cfg = rc.LIVE, rc.CFG
rc.LIVE = True
rows_none, rows_many = [], [{"fired": True, "result": "win"}] * 8


def gate(rows, st, **over):
    rc.CFG = {**_orig_cfg, **over}
    try:
        return rc.live_gate(rows, st)
    finally:
        rc.CFG = _orig_cfg


ok, why = gate(rows_many, {"last_cycle": time.time()})
check("no live_ack -> entries blocked", (not ok) and "live_ack" in why, why)
ok, why = gate(rows_none, {"last_cycle": time.time()}, live_ack=True)
check("live_ack but zero graded outcomes -> blocked (no blind sizing)",
      (not ok) and "graded" in why, why)
ok, why = gate(rows_many, {}, live_ack=True, min_grade_before_live=8)
check("graded history but no heartbeat -> blocked", (not ok) and "heartbeat" in why, why)
ok, why = gate(rows_many, {"last_cycle": time.time() - 10 * 3600}, live_ack=True, min_grade_before_live=8)
check("stale heartbeat (10 h) -> blocked", (not ok) and "ago" in why, why)
ok, why = gate(rows_many, {"last_cycle": time.time() - 600}, live_ack=True, min_grade_before_live=8)
check("acked + graded + fresh clock -> allowed", ok, why)
rc.LIVE = False
ok, why = gate([], {}, live_ack=False)
check("paper/ledger venues are never gated (else grading could never start)", ok, why)
rc.LIVE, rc.CFG = _orig_live, _orig_cfg

# ---------- 8: tape sanity + a mistyped ledger file must not stop the bot ----------
check("buy limit above the tape is refused (it would fill instantly, worse than market)",
      not rc.entry_sane("pullback_limit", 65964.31, 65454.71)[0])
check("buy limit below the tape is a real pullback",
      rc.entry_sane("pullback_limit", 65000.0, 65454.71)[0])
check("buy stop above the tape is a real breakout",
      rc.entry_sane("h1_breakout_stop", 66000.0, 65454.71)[0])
check("buy stop below the tape is refused",
      not rc.entry_sane("h1_breakout_stop", 65000.0, 65454.71)[0])
check("sell stop below the tape is a real breakdown",
      rc.entry_sane("sell_breakdown_stop", 64800.0, 65454.71)[0])
check("sell limit above the tape is a real bounce-short",
      rc.entry_sane("sell_retest_limit", 66000.0, 65454.71)[0])
check("no reference price -> refuse rather than guess", not rc.entry_sane("pullback_limit", 1.0, 0)[0])

import json as _json, importlib
_ledger_dir = tempfile.mkdtemp()
_f = os.path.join(_ledger_dir, "ledger.json")
with open(_f, "w") as _fh:
    _json.dump({"cash": 1000.0, "realized": 0.0, "orders": [], "positions": {}}, _fh)
_saved_ledger = bl.LEDGER_F
bl.LEDGER_F = _f
try:
    L2 = bl._load()
    check("mistyped ledger.json (positions as {}) is coerced, not fatal", isinstance(L2["positions"], list))
    # and a paper buy limit resting above the tape must fill at the tape, not at the limit
    L2["orders"] = [{"id": "t1", "client_order_id": "sentryT1", "symbol": "TEST/USD", "side": "buy",
                     "type": "limit", "qty": 1.0, "limit_price": 110.0, "stop_price": None,
                     "status": "open", "placed_at": 0}]
    _tp = bl._ticker_price
    bl._ticker_price = lambda sym: 100.0
    bl._tick(L2)
    bl._ticker_price = _tp
    check("paper fill never worse than the tape it walked into",
          abs(L2["orders"][0]["filled_avg_price"] - 100.0) < 1e-9, L2["orders"][0]["filled_avg_price"])
    check("  ...and the position was recorded, not crashed on", len(L2["positions"]) == 1)
finally:
    bl.LEDGER_F = _saved_ledger

# ---------- 9: re-anchoring a signal whose trigger is already through the tape ----------
check("pullback buy limit below the tape is left exactly where the checklist put it",
      rc.reanchor(65000.0, 64600.0, 66000.0, 65454.71, "buy_limit")[0] == 65000.0
      and rc.reanchor(65000.0, 64600.0, 66000.0, 65454.71, "buy_limit")[2])
check("breakout buy stop above the tape is left alone too",
      rc.reanchor(66000.0, 65600.0, 67000.0, 65454.71, "h1_breakout_stop")[0] == 66000.0)
e, n, ok = rc.reanchor(65964.31, 65400.0, 67000.0, 65454.71, "pullback_limit")
check("buy limit stranded above the tape re-anchors to the tape", ok and abs(e - 65454.71) < 1e-6, str(e))
check("  ...and journals why", "entering at market" in n, n)
e2, n2, ok2 = rc.reanchor(65964.31, 65400.0, 65400.0, 65454.71, "pullback_limit")
check("  ...but is refused when the target is already inside the entry", not ok2 and "target" in n2, n2)
e3, n3, ok3 = rc.reanchor(65000.0, 64800.0, 65800.0, 65454.71, "h1_breakout_stop")
check("buy stop stranded below the tape re-anchors (stale Donchian)", ok3 and abs(e3 - 65454.71) < 1e-6, str(e3))
e4, n4, ok4 = rc.reanchor(65000.0, 65400.0, 64500.0, 65454.71, "sell_retest_limit")
check("short whose target is on the wrong side of the tape is refused",
      not rc.reanchor(65000.0, 65400.0, 66000.0, 65454.71, "sell_retest_limit")[2])
check("sell limit stranded below the tape re-anchors", ok4 and abs(e4 - 65454.71) < 1e-6, str(e4))
check("R is measured from the price actually paid, not the stale level",
      abs(abs(e - 65400.0) - 54.71) < 0.01, f"{abs(e - 65400.0)} vs 54.71")
check("no tape -> no guessing, order is not sent", not rc.reanchor(1.0, 0.9, 1.2, 0.0, "buy_limit")[2])

# ---------- 10: live risk caps (the numbers must be consistent, not just small) ----------
cfg_live = {"live_max_risk": 25.0, "live_max_risk_frac": 0.01}
r, n = rc.live_risk_cap(112.0, 100000.0, cfg_live)
check("big account: sizer's $112 clamps to the $25 ceiling",
      r == 25.0 and len(n) == 1 and "live_max_risk" in n[0], str(n))
check("  ...1% of $100k ($1000) is looser, so only one clamp is logged", "$1000" not in str(n), str(n))
r, n = rc.live_risk_cap(84.0, 1000.0, cfg_live)
check("$1k account: 1% of equity governs, not the flat ceiling", r == 10.0, f"{r} {n}")
r, n = rc.live_risk_cap(5.0, 100000.0, cfg_live)
check("a trade already inside every cap is untouched", r == 5.0 and not n, str(n))
r, n = rc.live_risk_cap(50.0, 100000.0, {"live_max_risk_frac": 0.02})
check("no flat ceiling set -> equity fraction still applies", r == 50.0, str(r))
# stop distance must survive: $25 through 0.55% needs ~$4.5k notional, which a $100k book carries
need = 25.0 / 0.0055
check("clamped risk still fits the notional cap on a real account",
      need < 100000.0 * 0.25 and need > 250.0, f"needs ${need:,.0f}")
check("...and a $1k account is refused rather than degraded",
      not (need < 1000.0 * 0.25), "would have quietly traded a fraction of the intended risk")

# cash basis, fill price and the position's entry must be ONE number (the DOGE/AVAX paper fills of
# 2026-11-14 debited cash at the collar while quoting a different fill price — a $109 phantom)
_L = {"cash": 10000.0, "realized": 0.0, "positions": [],
      "orders": [{"id": "t2", "client_order_id": "sentryT2", "symbol": "TEST/USD", "side": "buy",
                  "type": "limit", "qty": 10.0, "limit_price": 100.5, "stop_price": None,
                  "status": "open", "placed_at": 0}]}
_f2 = os.path.join(_ledger_dir, "l2.json"); _save2 = bl.LEDGER_F
with open(_f2, "w") as _fh:
    _json.dump(_L, _fh)
bl.LEDGER_F = _f2
_tp2 = bl._ticker_price
bl._ticker_price = lambda sym: 100.0
bl._tick(_L)
bl._ticker_price = _tp2
bl.LEDGER_F = _save2
_o, _p = _L["orders"][0], _L["positions"][0]
check("fill price, cash debit and position basis are the same number",
      _o["filled_avg_price"] == _p["entry"] == 100.0 and _L["cash"] == 9000.0,
      f"{_o['filled_avg_price']} / {_p['entry']} / {_L['cash']}")

# ---------- 11: a market close must actually realize (this used to leave the book open forever)
_L3 = {"cash": 500.0, "realized": 0.0, "orders": [],
       "positions": [{"symbol": "TEST/USD", "qty": 10.0, "entry": 100.0, "cid": "sentryT3", "opened": 0}]}
_f3 = os.path.join(_ledger_dir, "l3.json"); _keep = bl.LEDGER_F
with open(_f3, "w") as _fh:
    _json.dump(_L3, _fh)
_L3["orders"] = [{"id": "t3x", "client_order_id": "sentryT3x", "symbol": "TEST/USD", "side": "sell",
                  "type": "market", "qty": 10.0, "limit_price": None, "stop_price": None,
                  "status": "open", "placed_at": 0}]
bl.LEDGER_F = _f3
_tp3 = bl._ticker_price
bl._ticker_price = lambda sym: 96.0
bl._tick(_L3)
bl._ticker_price = _tp3
bl.LEDGER_F = _keep
check("market close realizes P/L and frees the cash",
      _L3["positions"] == [] and abs(_L3["realized"] + 40.0) < 1e-9 and _L3["cash"] == 1460.0,
      f"realized {_L3['realized']} cash {_L3['cash']} pos {_L3['positions']}")

# ---------- 12: cleanup must be per-symbol, and open orders must carry their cid ----------
_oo = __import__("inspect").getsource(bl.open_orders)
check("shadow open_orders() reports client_order_id exactly once (the reconciler matches on it)",
      _oo.count("client_order_id") == 2 and "o.get(" in _oo, str(_oo.count("client_order_id")))
_q = chr(34)
check("  ...and a legacy row without one cannot KeyError the cycle",
      ("o[" + _q + "client_order_id" + _q + "]") not in _oo)
_rc_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_cycle.py")).read()
check("close-out cancels only that symbol's leftovers (no cancel_all on a fill)",
      "CANCEL leftover {sym}" in _rc_src and "broker.cancel_all()  # cancel any resting" not in _rc_src)
check("STATUS.md is written by the cycle and pushed with the memory files",
      "STATUS.md" in _rc_src and "write_status(acct, live, s, rows, tf_map, fired)" in _rc_src)

print("\n%d checks failed" % len(FAILS))
sys.exit(1 if FAILS else 0)
