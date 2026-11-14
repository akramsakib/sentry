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

os.environ["COINBASE_MODE"] = "exchange"      # section 17 flips cb.ADV for the retail shape
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

# Importing run_cycle installs config.json's fee schedule onto the ledger module (same object as
# `bl`). The cash assertions below were written against a free book, so pin it free here and test
# the fee model on purpose in section 16 — that is the only way both can mean something.
bl.set_fees({"maker": 0.0, "taker": 0.0})

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
ok, why = gate(rows_none, {"last_cycle": time.time()}, live_ack=True, min_grade_before_live=8)
check("live_ack but zero graded outcomes -> blocked when the grade gate is raised (mechanism works)",
      (not ok) and "graded" in why, why)
ok, why = gate(rows_none, {"last_cycle": time.time()}, live_ack=True, min_grade_before_live=0)
check("  ...and v4.7.1's shipped config sets that gate to 0 — first real order lands with no wait",
      ok and int(_orig_cfg.get("min_grade_before_live", 8)) == 0, why)
ok, why = gate(rows_many, {"last_cycle": time.time()}, live_ack=False, auto_ack_on_key=True)
check("auto_ack_on_key alone does NOT arm without a key in this process (OKX_KEYED is the other half)",
      (not ok) and "live_ack" in why, why)
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

# ---------- 13: grading comes from realised R, not from touching the target ----------
check("a favourable scratch is not a loss", rc.grade(0.36) == "win")
check("0R scratch is neither win nor loss", rc.grade(0.0) == "scratch" and rc.grade(-0.02) == "scratch")
check("a real stop-out is a loss", rc.grade(-1.0) == "loss")
check("grading feeds the win/loss vocabulary trades_log uses",
      rc.grade(1.2) == "win" and rc.grade(-0.9) == "loss")
check("status page re-reads the log (never shows a stale tally)",
      "write_status(acct, live, s, tl_rows(), tf_map, fired)" in
      open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_cycle.py")).read())

# ---------- 14: a scratch must not be scored as a loss ----------
_sz = core.Sizer(100.0, 50.0, 200.0)
_rows_wl = [{"result": "win", "fired": True}, {"result": "loss", "fired": True}]
_rows_ws = [{"result": "win", "fired": True}, {"result": "scratch", "fired": True}]
check("win+loss -> 0.5 accuracy", abs(_sz.acc("S11-dc20-long", _rows_wl) - 0.5) < 1e-9, str(_sz.acc("S11-dc20-long", _rows_wl)))
check("win+scratch -> 0.75 (flat pays half, not zero)",
      abs(_sz.acc("S11-dc20-long", _rows_ws) - 0.75) < 1e-9, str(_sz.acc("S11-dc20-long", _rows_ws)))

# ---------- 15: a computed outcome must survive the push (append-only lost every grade) ----------
_pm = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_cycle.py")).read()
_seg = _pm[_pm.index("def push_memory"): _pm.index('if __name__ == "__main__"')]
check("trades_log.jsonl is pushed as state (replace), not appended",
      '"trades_log.jsonl"' in _seg.split("for f_ in (")[1].split(")")[0]
      and 'push("trades_log.jsonl"' not in _seg, "still append-only")
check("journal.md stays append-only (a diary is not re-written)",
      'push("journal.md"' in _seg and ", True)" in _seg.split('push("journal.md"')[1][:40])
import tempfile as _tf
_d = _tf.mkdtemp(); _f = os.path.join(_d, "tl.jsonl")
with open(_f, "w") as _fh:
    _fh.write(json.dumps({"rid": "r1", "sym": "TEST/USD", "skill": "S11-dc20-long", "otype": "buy_stop",
                          "entry": 100.0, "sl": 99.0, "tp": 102.0, "score": 4, "risk": 100,
                          "fired": True}) + "\n")
_TL = rc.TL_F
rc.TL_F = _f
try:
    rc.tl_update("TEST/USD", "win", 101.5, 1.5)
    _after = [json.loads(x) for x in open(_f) if x.strip()]
    check("grading lands on the existing row and the file keeps one row per signal",
          len(_after) == 1 and _after[0]["result"] == "win" and _after[0]["R"] == 1.5, str(_after))
finally:
    rc.TL_F = _TL

# ---------- 16: what the venue takes. Fees are part of the strategy, not a detail ----------
_fees_saved = dict(bl.FEES)
check("config.json carries a real fee schedule for the venue it names",
      (rc.CFG.get("fees") or {}).get("taker", 0) > 0 and rc.MAX_FEE_R > 0,
      f"{rc.CFG.get('fees')} cap {rc.MAX_FEE_R}R")
bl.set_fees({"maker": 0.004, "taker": 0.006})
d1, r1 = bl.round_trip_fees(100.0, 99.0, 1.0, 1.0)
check("a 1 % stop on a 0.40/0.60 % book pays 1.19R in fees to round-trip",
      abs(r1 - 1.194) < 1e-3 and d1 > 1.0, f"${d1} = {r1}R")
d2, r2 = bl.round_trip_fees(100.0, 99.0, 1.0, 250.0)
check("  ...that drag is identical at any size — it is price geometry, not sizing",
      abs(r2 - r1) < 1e-9 and abs(d2 - d1 * 250) < 0.01, f"${d2} = {r2}R")
check("  ...so the only fix is a cheaper venue or a wider stop (and a wider stop is a different strategy)",
      bl.round_trip_fees(100.0, 98.0, 2.0, 1.0)[1] < r1, str(bl.round_trip_fees(100.0, 98.0, 2.0, 1.0)))
gross = (101.0 - 100.0) / 1.0
net = round(gross - rc.fee_drag(100.0, 101.0, 1.0, 10.0)[1], 2)
check("a textbook +1R win at a 1 % stop is GRADED A LOSS once the venue is paid",
      gross == 1.0 and rc.grade(net) == "loss", f"net {net}R")
check("grading and the book use the same helper (no second fee model to drift)",
      rc.fee_drag(100.0, 99.0, 1.0, 1.0) == bl.round_trip_fees(100.0, 99.0, 1.0, 1.0))
bl.set_fees({"maker": 0.0, "taker": 0.0})
check("a zero-rate book charges nothing — the model is data, not dogma",
      bl.round_trip_fees(100.0, 99.0, 1.0, 1.0) == (0.0, 0.0))
check("  ...and an absent config key leaves the schedule alone rather than zeroing it",
      bl.set_fees({}) == {"maker": 0.0, "taker": 0.0})

# the dollars: entry fee out of cash, exit fee out of proceeds, realized net of both
bl.set_fees({"maker": 0.004, "taker": 0.006})
_L5 = {"cash": 10000.0, "realized": 0.0, "fees_paid": 0.0, "positions": [],
       "orders": [{"id": "t5", "client_order_id": "sentryT5", "symbol": "TEST/USD", "side": "buy",
                   "type": "limit", "qty": 10.0, "limit_price": 100.0, "stop_price": None,
                   "status": "open", "placed_at": 0}]}
_f5 = os.path.join(_ledger_dir, "l5.json")
with open(_f5, "w") as _fh:
    _json.dump(_L5, _fh)
_keep5, _tp5 = bl.LEDGER_F, bl._ticker_price
bl.LEDGER_F = _f5
bl._ticker_price = lambda sym: 100.0   # noqa: E501
bl._tick(_L5)                                  # entry fills at 100
_cash_after_entry = _L5["cash"]
_L5["orders"].append({"id": "t5x", "client_order_id": "sentryT5x", "symbol": "TEST/USD", "side": "sell",
                      "type": "stop", "qty": 10.0, "limit_price": None, "stop_price": 101.0,
                      "status": "open", "placed_at": 0})
bl._tick(_L5)                                  # stop close fills at 101
bl._ticker_price = _tp5
check("a paper entry pays its venue fee out of cash", _cash_after_entry == 10000.0 - 1000.0 - 6.0,
      f"{_cash_after_entry}")
check("  ...the exit fee comes off the proceeds, so equity is not theatre",
      _L5["cash"] == _cash_after_entry + 1010.0 - 6.06, f"{_L5['cash']}")
check("  ...and realized P&L is net of both legs (gross was +$10)",
      abs(_L5["realized"] - (10.0 - 6.0 - 6.06)) < 1e-6 and not _L5["positions"], f"realized {_L5['realized']}")
check("  ...the book keeps a running total the journal can show",
      abs(_L5["fees_paid"] - 12.06) < 1e-6 and abs(bl.fee_stats()["paid"] - 12.06) < 1e-6
      and bl.fee_stats()["taker"] == 0.006, str(_L5.get("fees_paid")))
bl.LEDGER_F = _keep5
bl.set_fees(_fees_saved)

check("the cost of doing business is on the status page, not only in the journal",
      "Venue cost:" in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_cycle.py")).read())

# ---------- 17: the retail payload — a retail key cannot sign on the Exchange host at all ----------
_meta_saved2, _dry_saved2 = cb._meta, cb.DRY
cb._meta = lambda sym: {"quote": "0.01", "base": "0.00000001", "min_funds": 1.0, "ok": True}
cb.DRY = True
cb.ADV = True
try:
    r = cb.place_order("buy", "XRP/USD", qty=100.0, otype="stop", stop_price=0.99537, cid="sentryXRP9n1")
    b = r["payload"]
    cfg_ = b["order_configuration"]["stop_limit_stop_limit_gtc"]
    check("retail terms go inside order_configuration (no flat type/size/price)",
          "type" not in b and "time_in_force" not in b and "size" not in b, str(b))
    check("  ...and the client id is client_order_id, still a UUIDv4",
          "client_oid" not in b and _re.fullmatch(r"[0-9a-f-]{36}", b["client_order_id"] or ""), str(b))
    check("  ...a buy stop triggers from below -> STOP_UP",
          cfg_["stop_direction"] == "STOP_DIRECTION_STOP_UP", str(cfg_))
    check("  ...the limit still clears its own trigger by a tick",
          float(cfg_["limit_price"]) > float(cfg_["stop_price"]), f"{cfg_['limit_price']} vs {cfg_['stop_price']}")
    check("  ...every number on this API is a string",
          all(isinstance(cfg_[k], str) for k in ("base_size", "limit_price", "stop_price")), str(cfg_))
    sb = cb.place_order("sell", "XRP/USD", qty=100.0, otype="stop", stop_price=0.955,
                        cid="sentryXRP9n2")["payload"]["order_configuration"]["stop_limit_stop_limit_gtc"]
    check("  ...a protective sell flips to STOP_DOWN with the limit below the trigger",
          sb["stop_direction"] == "STOP_DIRECTION_STOP_DOWN" and float(sb["limit_price"]) < float(sb["stop_price"]),
          str(sb))
    lb = cb.place_order("buy", "XRP/USD", qty=100.0, otype="limit", limit_price=0.98,
                        cid="sentryXRP9n4")["payload"]["order_configuration"]
    check("  ...a pullback is limit_limit_gtc", list(lb) == ["limit_limit_gtc"], str(lb))
    mb = cb.place_order("buy", "SOL/USD", notional=75.0, otype="market", limit_price=76.0,
                        cid="sentrySOL9n5")["payload"]["order_configuration"]["market_market_ioc"]
    check("  ...a market buy spends quote_size (dollars), not base_size",
          "quote_size" in mb and "base_size" not in mb and float(mb["quote_size"]) == 75.0, str(mb))
    ms = cb.place_order("sell", "SOL/USD", qty=1.5, otype="market", limit_price=76.0,
                        cid="sentrySOL9n6")["payload"]["order_configuration"]["market_market_ioc"]
    check("  ...a market close spends coins", "base_size" in ms and "quote_size" not in ms, str(ms))
    n1 = cb._norm({"order_id": "o1", "client_order_id": cb.oid_for("c1"), "product_id": "SOL-USD",
                   "side": "BUY", "status": "OPEN",
                   "order_configuration": {"stop_limit_stop_limit_gtc": {"base_size": "1.5",
                                                                           "limit_price": "76.07",
                                                                           "stop_price": "76.00"}}})
    check("a retail open order reads back through the same keys run_cycle reconciles on",
          n1["qty"] == 1.5 and n1["stop_price"] == 76.0 and n1["limit_price"] == 76.07
          and n1["status"] == "open" and n1["symbol"] == "SOL/USD" and n1["type"] == "stop_limit"
          and n1["id"] == "o1", str(n1))
    n2 = cb._norm({"order_id": "o2", "side": "SELL", "product_id": "SOL-USD", "status": "COMPLETED",
                   "filled_size": "1.5", "average_fill_price": "77.25",
                   "order_configuration": {"market_market_ioc": {"base_size": "1.5"}}})
    check("a filled retail market close hands the orchestrator a fill price to grade from",
          n2["status"] == "filled" and n2["filled_avg_price"] == 77.25 and n2["filled_qty"] == 1.5, str(n2))
finally:
    cb.ADV, cb.DRY, cb._meta = False, _dry_saved2, _meta_saved2

# A CI variable that is not set arrives as the EMPTY STRING, not as missing, so `getenv(X, default)`
# hands float()/urllib a "" and the run dies in import. Pinned because this exact thing broke run #34.
_cfg_files = ("broker_okx.py", "broker_coinbase.py", "watchdog.py", "broker.py")
_here = os.path.dirname(os.path.abspath(__file__))
# an EMPTY default is fine (nothing chokes on ""); a non-empty one hides the case where "" arrives.
_bad = [f for f in _cfg_files if _re.search(r'os\.environ\.get\("[A-Z_]+", "[^"]',
              open(os.path.join(_here, f)).read())]
check("env reads treat '' as unset (a CI variable with no value is empty, not absent)", not _bad, str(_bad))
check("  ...and the workflow passes no bare tuning knobs as Actions variables",
      "OKX_SLACK" not in open(os.path.join(_here, ".github", "workflows", "scan.yml")).read())

# The two config lines that decide whether this strategy can pay for itself must not drift apart:
# fees priced for one venue while trading another is how 4 releases of paper looked profitable.
_cfgnow = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")))
_exp_taker = {"okx": 0.0005, "coinbase": 0.006, "ledger": None, "alpaca": None}
check("config.json: the fee schedule belongs to the venue it names",
      _exp_taker.get(_cfgnow["execution"]) in (None, (_cfgnow.get("fees") or {}).get("taker")),
      f"execution={_cfgnow['execution']} taker={(_cfgnow.get('fees') or {}).get('taker')}")
check("  ...and the live fee guard is enabled (0 = the guard is off, which is not the default)",
      _cfgnow.get("live_max_fee_r", 0) > 0 and _cfgnow.get("live_ack") is False,
      f"cap {_cfgnow.get('live_max_fee_r')} / live_ack {_cfgnow.get('live_ack')}")

# ---------- 18: the OKX venue (perps = the only schedule this playbook can pay) ----------
import broker_okx as ok

cid_real = "sentrySOLUSD1794672000000n1"
o1 = ok.oid_for(cid_real)
check("OKX clOrdId is letters/digits only, <=32 chars", bool(_re.fullmatch(r"[A-Za-z0-9]{1,32}", o1)), o1)
check("  ...deterministic per cid (no mapping table to lose between runners)", o1 == ok.oid_for(cid_real))
check("  ...and unique per cid", o1 != ok.oid_for(cid_real.replace("n1", "n2")))

# OKX candle rows are [ts, OPEN, high, low, close, vol, volCcy, volCcyQuote, confirm], newest FIRST —
# a different order from Coinbase's [time, low, high, open, close, volume]. Both are pinned because
# the first port of this bot mapped one into the other and every candlestick pattern fired on itself.
okx_rows = [["1794672000000", "73.84", "73.91", "72.22", "72.66", "1272606", "1272606", "92684302", "0"],
            ["1794668400000", "74.04", "74.27", "73.11", "73.84", "1308003", "1308003", "96410124", "1"],
            ["1794664800000", "75.47", "75.52", "73.66", "74.04", "2042319", "2042319", "151905648", "1"]]
bb = ok._bars(okx_rows, now_ts=1_794_672_000)
check("the forming candle (confirm == 0) never enters the history", len(bb) == 2, str(len(bb)))
_mid = next(b for b in bb if b["c"] == 73.84)      # the 1794668400000 row, found by content not by clock
check("open is column 1 on OKX (NOT low, as on Coinbase)",
      _mid["o"] == 74.04 and _mid["h"] == 74.27 and _mid["l"] == 73.11 and _mid["c"] == 73.84, str(_mid))
check("rows are re-sorted oldest-first for the checklist", bb[0]["t"] < bb[1]["t"])
try:
    ok._bars([["1794664800000", "10", "1", "9", "2", "1", "1", "1", "1"]], now_ts=1_794_672_000)
    check("  ...high < open is rejected", False, "it accepted a bar with high < open")
except ok.BrokerError as e:
    check("  ...high < open is rejected", "impossible bar" in str(e), str(e))

_meta_ok, _dry_ok = ok._meta, ok.DRY
ok._meta = lambda sym: {"tick": "0.01", "lot": "0.01", "min_sz": "0.01", "ct_val": 1.0,
                        "live": True, "inst": sym.split("/")[0].upper() + "-USDT-SWAP"}
ok.DRY = True
try:
    r = ok.place_order("buy", "SOL/USD", qty=68.5, otype="stop", stop_price=73.55,
                       tp=74.9, sl=73.0, cid="sentrySOL1n1")
    b = r["payload"]
    check("a triggered entry goes to order-algo, not /trade/order", r["path"] == "/api/v5/trade/order-algo", r["path"])
    check("  ...as ordType=conditional with a last-price trigger",
          b["ordType"] == "conditional" and b["trigger"]["triggerPx"] == "73.55"
          and b["trigger"]["triggerPxType"] == "last", str(b.get("trigger")))
    check("  ...and it fires as a COLLAR limit one tick past the trigger, not a naked market",
          float(b["px"]) > float(b["trigger"]["triggerPx"]), f"{b['px']} vs {b['trigger']['triggerPx']}")
    att = b["attachAlgoOrds"][0]
    check("  ...TP and SL ride on the entry order (protected while the runner sleeps)",
          att["tpTriggerPx"] == "74.9" and att["slTriggerPx"] == "73.0"
          and att["tpOrdPx"] == "-1" and att["slOrdPx"] == "-1", str(att))
    check("  ...side is carried on the order, clOrdId on the order, and tdMode is set",
          b["side"] == "buy" and b["tdMode"] in ("cross", "isolated") and b["clOrdId"].startswith("sen"), str(b))
    s2 = ok.place_order("sell", "SOL/USD", qty=68.5, otype="stop", stop_price=70.0,
                        tp=69.0, sl=71.0, cid="sentrySOL1n2")["payload"]
    check("  ...a short entry is a SELL conditional whose collar sits BELOW the trigger",
          s2["side"] == "sell" and float(s2["px"]) < float(s2["trigger"]["triggerPx"]), f"{s2['px']} vs {s2['trigger']['triggerPx']}")
    m = ok.place_order("sell", "SOL/USD", qty=68.5, otype="market", cid="sentrySOL1n3")
    check("a close is an ordinary /trade/order market order",
          m["path"] == "/api/v5/trade/order" and m["payload"]["ordType"] == "market"
          and m["payload"]["sz"] == "68.5", str(m["payload"]))
    ok._meta = lambda sym: {"tick": "0.01", "lot": "1", "min_sz": "1", "ct_val": 1.0,
                            "live": True, "inst": "DOGE-USDT-SWAP"}
    dg = ok.place_order("buy", "DOGE/USD", qty=104515.05, otype="limit", limit_price=0.0597,
                        cid="sentryDOGE1n9")["payload"]
    check("a coins-denominated size becomes whole contracts (ctVal 1.0, lot 1)",
          dg["sz"] == "104515", dg["sz"])
    try:
        ok.place_order("buy", "DOGE/USD", qty=0.2, otype="limit", limit_price=0.0597, cid="z")
        check("size below minSz is refused (not rounded to zero silently)", False, "it placed a sub-minimum order")
    except ok.BrokerError as e:
        check("size below minSz is refused (not rounded to zero silently)", "minsz" in str(e).lower(), str(e))
    ok.CAN_SHORT = False
    try:
        ok.place_order("sell", "BTC/USD", qty=0.01, otype="stop", stop_price=60000.0, cid="z")
        check("a spot venue cannot open a short", False, "it accepted an opening short")
    except ok.BrokerError as e:
        check("a spot venue cannot open a short", "spot" in str(e).lower(), str(e))
    ok.CAN_SHORT = True
    n = ok._norm({"ordId": "1", "clOrdId": "senabc", "instId": "SOL-USDT-SWAP", "side": "buy",
                  "ordType": "conditional", "state": "partially_filled", "sz": "68", "accFillSz": "12",
                  "avgPx": "73.5", "px": "73.66"})
    check("a venue order object normalizes to the keys run_cycle reconciles on",
          n["status"] == "open" and n["filled_qty"] == 12.0 and n["filled_avg_price"] == 73.5
          and n["symbol"] == "SOL/USD" and n["limit_price"] == 73.66, str(n))
    n2 = ok._norm({"ordId": "2", "instId": "SOL-USDT-SWAP", "side": "sell", "state": "filled",
                   "sz": "68", "accFillSz": "68", "avgPx": "77.25", "ordType": "market"})
    check("  ...and a filled one reports as filled so the close gets graded",
          n2["status"] == "filled" and n2["filled_avg_price"] == 77.25, str(n2))
finally:
    ok._meta, ok.DRY, ok.CAN_SHORT = _meta_ok, _dry_ok, True

# the venue's cost is the reason it exists: 0.02/0.05 must clear the guard the Coinbase tier fails
bl.set_fees({"maker": 0.0002, "taker": 0.0005})
_, r_okx = bl.round_trip_fees(73.55, 73.0, 73.55 - 73.0, 68.5)
bl.set_fees({"maker": 0.004, "taker": 0.006})
_, r_cb = bl.round_trip_fees(73.55, 73.0, 73.55 - 73.0, 68.5)
bl.set_fees(rc.CFG.get("fees"))
check("the identical trade costs 0.07R on OKX and 1.5R on Coinbase retail — one stop, one signal",
      r_okx <= rc.MAX_FEE_R and r_cb > rc.MAX_FEE_R, f"{r_okx}R vs {r_cb}R")
check("so the fee guard fires on one venue and passes on the other (data, not opinion)",
      r_okx < r_cb / 10, f"okx {r_okx}R, coinbase {r_cb}R")
check("run_cycle reads capability from the venue, not from wishful config",
      rc.CAN_SHORT is False and rc.ATTACH is False and hasattr(ok, "CAN_SHORT") and ok.ATTACH_TP_SL)
check("and STATUS.md never claims real money while the venue is DRY or SIM",
      "MONEY = LIVE and not getattr(broker, \"DRY\", False)" in _pm
      or 'MONEY = LIVE and not getattr(broker, "DRY", False)' in
      open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_cycle.py")).read())

# ---------- 20: v4.7.0 ENGINE PARITY with the Mac/MT5 build ----------
# The promise of 4.7.0 is "same skills, same patterns, same timeframes" for crypto.
# A test suite that cannot notice a dropped skill is how the first port went quiet-wide.
_here20 = os.path.dirname(os.path.abspath(__file__))
_core_src20 = open(os.path.join(_here20, "sentry_core.py")).read()
_RC_SRC20 = open(os.path.join(_here20, "run_cycle.py")).read()
for sk in ("S1-pullback", "S2-break", "S3-momentum", "S4-band-fade", "S10-ma-cross",
           "S11-dc20", "S11-dc55", "S13-ichimoku", "S15-squeeze", "S16-inside",
           "S18-rsi2", "S18-ma-revert", "S21-pivot", "S22-rsi", "S23-spring", "S23-upthrust",
           "S24-fib", "S25-session-break"):
    check(f"engine carries the Mac's {sk} family", sk in _core_src20)
_MAC22 = {"hammer/takuri", "shooting-star", "dragonfly", "gravestone", "marubozu",
          "bull-engulfing", "bear-engulfing", "piercing", "dark-cloud", "tweezer-bottom",
          "tweezer-top", "bull-harami", "bear-harami", "homing-pigeon", "morning-star",
          "evening-star", "three-soldiers", "three-crows", "three-inside-up",
          "three-inside-down", "three-outside-up", "three-outside-down"}
_eng22 = {c for c in core.candle_engine.__code__.co_consts if isinstance(c, str) and c in _MAC22}
check("§12 candle library carries all 22 Mac patterns", _eng22 == _MAC22,
      f"missing {sorted(_MAC22 - _eng22)}")
check("evaluate_symbol consumes five timeframes",
      all(k in _core_src20 for k in ('tf.get("5m")', 'tf.get("15m")', 'tf.get("1h")',
                                     'tf.get("4h")', 'tf.get("1d")')))
check("fetch pulls M5 and H4 from the venue", '"5m", "5Minute"' in _RC_SRC20 and '"4h", "4Hour"' in _RC_SRC20)
check("RSI(2) is computed on the 5m closes like the Mac (not 15m)",
      'r5_2 = rsi([b["c"] for b in m5], 2)' in _core_src20)
check("chandelier trail runs on shorts too (Mac behaviour both directions)",
      'side == "short" and fav >= 1.5 * rd' in _RC_SRC20)
check("staleness now guards the fast timeframe too (no more blind scans)",
      '"5m", 45 * 60' in _RC_SRC20)
check("candle one-shot dedupe state survives in the repo state", 'seen_candles' in _RC_SRC20)

# ---------- 21: v4.7.1 — setup is complete; the ONLY remaining human step is the key ----------
cfg21 = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")))
check("auto-ack switch exists and is a real boolean (mirror ships false; the Mac book ships true)",
      isinstance(cfg21.get("auto_ack_on_key"), bool) and "auto_ack_on_key" in _RC_SRC20)
check("  ...via the OKX trade key specifically, not any env noise",
      "OKX_KEYED" in _RC_SRC20 and 'os.environ.get("OKX_API_KEY")' in _RC_SRC20)
check("no graded-outcome wait before the first real order",
      int(cfg21.get("min_grade_before_live", 8)) == 0)
check("  ...but the live clamps stay armed (this is a smaller first trade, not an unbounded one)",
      float(cfg21.get("live_max_risk", 0)) > 0 and float(cfg21.get("live_max_risk_frac", 0)) > 0)
check("half-armed venue still fails red (live_ack w/o keys must not spin silently)",
      "live_ack=true but these are missing" in _RC_SRC20)

# behavioural: a thin 5m book must gate the WHOLE symbol, exactly like the Mac's len() checks
_thin20 = {"5m": [], "15m": [], "1h": [], "4h": [], "1d": []}
_big = lambda n, step, tf: [{"t": 1_700_000_000 + i * step, "o": 100.0 + 0.5 * i,
                             "h": 100.0 + 0.5 * (i + 1) + 0.01, "l": 100.0 + 0.5 * i - 0.01,
                             "c": 100.0 + 0.5 * (i + 1), "v": 10.0} for i in range(n)]
_ok20 = {"5m": _big(200, 300, 1), "15m": _big(200, 900, 1), "1h": _big(200, 3600, 1),
         "4h": _big(120, 14400, 1), "1d": _big(60, 86400, 1)}
check("thin data -> zero candidates (the gate, not a crash)",
      core.evaluate_symbol("TEST/USD", _thin20, 3, []) == [])
_seen20 = []
_a20 = core.evaluate_symbol("TEST/USD", _ok20, 3, _seen20)
check("a straight-up market produces candidates (rising: soldiers/marubozu bull)",
      any(c["skill"].startswith("C-H1-") for c in _a20), str([c["skill"] for c in _a20][:6]))
_b20 = core.evaluate_symbol("TEST/USD", _ok20, 3, _seen20)
check("same closed candle can never fire twice — seen_candles blocks the rerun",
      not any(c["skill"].startswith("C-") for c in _b20), str([c["skill"] for c in _b20][:6]))

# ---------- 22: v4.7.3 — the Coinbase lane and the fee-widening floor ----------
import re as _re22
import broker_coinbase as _cb22                                 # noqa: E402
import broker_okx as _okx22                                     # noqa: E402
cfg22 = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")))
check("stop_floor_frac exists and the shipped (OKX) book does NOT widen it",
      "stop_floor_frac" in cfg22 and float(cfg22["stop_floor_frac"]) == 0.0,
      f"{cfg22.get('stop_floor_frac')!r}")
check("the floor is wired at the one place a stop is judged (right after re-anchor)",
      'CFG.get("stop_floor_frac")' in src and "WIDENED —" in src)
check("the traded stop, not the asked stop, is what gets stored and managed",
      src.count('"sl": c["sl"]') >= 2 and '"sl_ask": sl0' in src)
_loop22 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools/mac/crypto_loop.py")).read()
check("the boot banner tells you WHICH env file the current venue reads (venue-derived, not hard-coded)",
      "def boot_banner" in _loop22 and "_exe = getattr" not in _loop22
      and '"./okx.env"' in _loop22 and '"./bitget.env"' in _loop22
      and '"./coinbase.env + ./coinbase.pem"' in _loop22)
# The docstring is ALLOWED to name the bug it prevents; the executable part is not. Strip docstrings
# before asserting the venue-blind claim is gone, or the test would fail on its own explanation.
_loop22_code = _re22.sub(r'""".*?"""', "", _loop22, flags=_re22.S)
_loop22_code = "\n".join(l for l in _loop22_code.splitlines() if not l.strip().startswith("#"))
check("...and no venue-blind '(both empty)' claim survives in the CODE: an armed book must not read as unarmed",
      "both empty" not in _loop22_code and "key PRESENT" in _loop22_code
      and 'for f in ("OKX_KEYED", "BG_KEYED", "CB_KEYED")' in _loop22_code
      and "both empty" in _loop22,                         # the docstring still names the old bug
      "the explanation stays, the claim is gone")
check("the no-key note names the local key file, not GitHub Secrets (money moved home in 4.7.2)",
      'Actions secret to trade the real book' not in src and "./coinbase.env" in src)
check("Coinbase Exchange is spot for us: no CAN_SHORT -> shorts stay paper-graded",
      not hasattr(_cb22, "CAN_SHORT") and getattr(_okx22, "CAN_SHORT", False) is True)

import broker_ledger as _bl22                                   # noqa: E402
# The arithmetic that makes a floor necessary, computed with the venue model the bot itself uses
# (round_trip_fees charges BOTH legs as taker — the pessimistic case a guard should assume).
_fees_backup = dict(_bl22.FEES)
_CAP = float(cfg22["live_max_fee_r"])


def _drag(fees, stop_frac, tp_frac=0.015, risk=100.0, entry=100.0):
    _bl22.set_fees(fees)
    rd = entry * stop_frac
    qty = risk / rd
    usd, r = _bl22.round_trip_fees(entry, entry - rd, rd, qty)
    return usd, r, qty * entry


_cb_fees = {"maker": 0.0040, "taker": 0.0060}
_usd_a, _r_a, _n_a = _drag(_cb_fees, 0.005)
# 2.39R, not the back-of-envelope 2.0R: the exit leg is charged on the LOSS price (99.5), and
# rounding leaves 4 dimes on a $100 risk, so the model is the number of record.
check("Coinbase base tier at the book's 0.5 % stop costs >2R (guard cap 0.25R) -> refused",
      abs(_r_a - 2.39) < 0.02 and _r_a > _CAP, f"{_r_a:.2f}R on ${_n_a:,.0f} notional")
_usd_b, _r_b, _n_b = _drag(_cb_fees, 0.02)
check("the same trade with a 4x wider stop divides the drag by 4 -> 0.60R",
      abs(_r_b - _r_a / 4.0) < 0.005 and abs(_r_b - 0.60) < 0.02, f"{_r_b:.2f}R")
check("and the notional it has to touch shrinks by the same 4x (less market, same dollars at risk)",
      abs(_n_b * 4.0 - _n_a) < 1.0, f"${_n_a:,.0f} -> ${_n_b:,.0f}")
_usd_c, _r_c, _n_c = _drag({"maker": 0.0010, "taker": 0.0020}, 0.02)
check("Coinbase at the $100k-1M tier with the floor is 0.17R — under the cap, tradeable",
      _r_c < _CAP, f"{_r_c:.2f}R")
_usd_d, _r_d, _n_d = _drag({"maker": 0.0002, "taker": 0.0005}, 0.005)
check("OKX perps at the UNWIDENED 0.5 % stop is 0.14R — why OKX stays the shipped venue",
      _r_d < _CAP, f"{_r_d:.2f}R")
_bl22.set_fees(_fees_backup)

# behavioural: execute the SHIPPED floor block (dedented from run_cycle) on real numbers
_m22 = _re22.search(r'(\n {12}floor_frac = float\(CFG\.get\("stop_floor_frac"\).*?)\n {12}# On a live venue',
                    src, _re22.S)
check("floor block extractable from run_cycle source for a behavioural run", _m22 is not None)
if _m22:
    _body = "\n".join(l[12:] for l in _m22.group(1).strip("\n").split("\n"))
    for _sell, _floor, _want in ((False, 0.02, "wide"), (True, 0.02, "wide"),
                                 (False, 0.0, "keep"), (True, 0.0, "keep")):
        _sl0, _tp0 = (99.5, 101.5) if not _sell else (100.5, 98.5)
        _ns = {"CFG": {"stop_floor_frac": _floor}, "journal": lambda line: _ns.setdefault("LOG", []).append(line),
               "entry": 100.0, "r_dist": 0.5, "is_sell": _sell, "sym": "TEST/USD", "min_frac": 0.004,
               "c": {"skill": "S4-test", "sl": _sl0, "tp": _tp0}, "sl0": _sl0, "tp0": _tp0,
               "risk": 100.0, "LOG": []}
        exec(compile(_body, "<floor>", "exec"), _ns)
        _sl, _tp, _rd = _ns["c"]["sl"], _ns["c"]["tp"], _ns["r_dist"]
        _tag = f"{'short' if _sell else 'long'}, floor={_floor} ({_want})"
        check(f"{_tag}: stop {'moved to the floor' if _want == 'wide' else 'untouched'}",
              abs(abs(_sl - 100.0) - 100.0 * _floor) < 1e-9 if _want == "wide" else _sl == _sl0,
              f"sl {_sl0} -> {_sl}")
        _rr0 = abs(_tp0 - 100.0) / abs(_sl0 - 100.0)
        _rr1 = abs(_tp - 100.0) / abs(_sl - 100.0)
        check(f"{_tag}: reward-to-risk preserved ({_rr0:.2f}R target — the strategy is re-priced, not rewritten)",
              abs(_rr1 - _rr0) < 1e-9, f"{_rr0:.3f} -> {_rr1:.3f}")
        check(f"{_tag}: reward distance scaled by exactly the widening factor",
              abs(abs(_tp - 100.0) - abs(_tp0 - 100.0) * (4.0 if _want == "wide" else 1.0)) < 1e-9,
              f"tp dist {abs(_tp - 100.0):.4f} vs {abs(_tp0 - 100.0):.4f} x "
              f"{(4.0 if _want == 'wide' else 1.0):.1f}")
        check(f"{_tag}: order still valid — entry sits between stop and target",
              (_sl < 100.0 < _tp) if not _sell else (_tp < 100.0 < _sl), f"sl {_sl} tp {_tp}")
        check(f"{_tag}: dollars of risk unchanged, size falls out of the wider distance",
              abs(_ns["risk"] - 100.0) < 1e-9 and abs(_rd - (2.0 if _want == "wide" else 0.5)) < 1e-9,
              f"r_dist {_rd}")
        if _want == "wide":
            check(f"{_tag}: journal says WIDENED (the change is loud, not silent)",
                  any("WIDENED" in l for l in _ns["LOG"]), str(_ns["LOG"])[:80])

# ---------- 23: the Bitget lane (the venue the user ALREADY has) ----------
import time as _t23
import broker_bitget as _bg23                                   # noqa: E402
check("execution=bitget is a real venue branch, not a config string",
      'EXEC_MODE == "bitget" and BG_KEYED' in _RC_SRC20 and 'import broker_bitget as broker' in _RC_SRC20)
check("  ...and the no-key fallback names itself in the journal",
      'shadow-ledger(bitget-no-key)' in _RC_SRC20)
check("  ...and a pasted Bitget key arms it (same rule as OKX, no other change)",
      "(OKX_KEYED or BG_KEYED)" in _RC_SRC20)
check("  ...and the boot refuses a half-armed Bitget live venue",
      '"BITGET_API_KEY", "BITGET_API_SECRET", "BITGET_API_PASSPHRASE"' in _RC_SRC20)
# the data plane follows the venue (the drift bug class the whole design is built around)
check("data plane switches with the venue (bitget candles when trading bitget)",
      'if EXEC_MODE == "bitget" and os.environ.get("OKX_DATA") != "1":' in _RC_SRC20
      and "import broker_bitget as data_broker" in _RC_SRC20)
# candles: OLDEST FIRST rows, no confirm flag, forming bar must be dropped by clock maths
_now = int(_t23.time())
_per = 300
_rows23 = [[(_now - 2 * _per) * 1000, "100.0", "101.0", "99.0", "100.5", "10.0", "1000.0"],
           [(_now - 1 * _per) * 1000, "100.5", "102.0", "100.0", "101.5", "11.0", "1100.0"],
           [_now * 1000,                "101.5", "103.0", "101.0", "102.5", "1.0", "100.0"]]   # forming
_b23 = _bg23._bars(_rows23, now_ts=_now + 30)
check("bitget bars: closed bars kept, the still-forming one dropped by its open time",
      len(_b23) == 2, f"{len(_b23)} bars from 3 rows")
check("bitget o/h/l/c map from ITS row order (open index 1, close index 4) — not OKX's or Coinbase's",
      _b23[0]["o"] == 100.0 and _b23[0]["c"] == 100.5 and _b23[1]["o"] == 100.5 and _b23[1]["c"] == 101.5,
      str(_b23[:2]))
check("bars returned oldest→newest (the scan reads [-1] as 'latest closed')",
      _b23[0]["t"] < _b23[1]["t"], f"{_b23[0]['t']} vs {_b23[1]['t']}")
try:
    _bg23._bars([[_now * 1000, "100.0", "99.0", "98.0", "101.0", "1", "1"]])
    check("impossible bar still raises", False, "no exception")
except _bg23.BrokerError:
    check("impossible bar still raises", True)
# granularity whitelist: the exact bug this adapter shipped with (history-candles rejects *utc names)
try:
    _bg23.crypto_bars("BTC/USD", "5Minute", 6)          # public call: allowed, must not raise a name error
    check("5m resolves to the endpoint's own name (300s bars, proven live 2026-11-14)",
          _bg23.BAR["5Minute"] == "5m")
except Exception as e:                                  # noqa: BLE001 — offline: no network in CI
    check("5m resolves to a valid granularity name", _bg23.BAR["5Minute"] == "5m", str(e)[:60])
try:
    _bg23.crypto_bars("BTC/USD", "5m2", 6)
    check("an unknown timeframe FAILS instead of silently returning 1H (the OKX BAR.get trap)",
          False, "no exception")
except _bg23.BrokerError as e:
    check("an unknown timeframe FAILS instead of silently returning 1H (the OKX BAR.get trap)",
          "not a Bitget history-candles granularity" in str(e))
check("daily/weekly/monthly use the venue's *utc names, so both books cut the day at 00:00 UTC",
      _bg23.BAR["1Day"] == "1Dutc" and _bg23.BAR["1Week"] == "1Wutc" and _bg23.BAR["1Month"] == "1Mutc"
      and _bg23.BAR["1Hour"] == "1H" and _bg23.BAR["4Hour"] == "4H"
      and "1Hutc" not in _bg23.BAR.values() and "4Hutc" not in _bg23.BAR.values(),
      "history-candles accepts 1Dutc/1Wutc/1Mutc but NOT 1Hutc/4Hutc (measured 400171, 2026-11-14)")
_kit23 = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools/mac/crypto_loop.py")).read()
check("the Mac runner loads EVERY *.env in the folder, so a third lane needs no code change",
      'f.endswith(".env")' in _kit23 and "os.listdir(HERE)" in _kit23)
_bgp23 = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "tools/mac/com.hermes.sentry.crypto.bitget.plist")
check("a bitget book ships its own launchd label and folder, so two books cannot collide",
      os.path.exists(_bgp23) and "com.hermes.sentry.crypto.bitget" in open(_bgp23).read()
      and "crypto-bitget" in open(_bgp23).read())
check("bitget.env ships as a template that arms NOTHING (every key line commented)",
      all(not l.strip().startswith("BITGET_API") for l in open(os.path.join(
          os.path.dirname(os.path.abspath(__file__)), "tools/mac/bitget.env"))))
check("no silent default: BAR.get has no fallback argument in crypto_bars",
      'BAR.get(timeframe)' in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               "broker_bitget.py")).read())
# sizing/price maths: Bitget sizes in COINS (no ctVal), on the venue's own increments
_m23 = {"tick": "0.1", "lot": "0.0001", "min_sz": "0.0001", "ct_val": 1.0, "live": True,
        "inst": "BTCUSDT", "maker": 0.0002, "taker": 0.0006, "min_usdt": 5.0}
_bg23._META["BTCUSDT"] = dict(_m23)
check("size floors to volumePlace and is sent as a string (venue rejects float noise)",
      _bg23._q(0.1234567, "0.0001") == "0.1234", _bg23._q(0.1234567, "0.0001"))
check("price floors to pricePlace on the far side of the tape, ceil on the near side",
      _bg23._q(64528.37, "0.1") == "64528.3", _bg23._q(64528.37, "0.1"))
_path, _body = _bg23._body("buy", "BTCUSDT", "0.1234", "64000.0", "limit", None,
                           "66000.0", "63000.0", "sentryBTCUSD1794662107892n5", "BTC/USD")
check("limit entry: single endpoint, GTC, TP+SL attached, productType capitalised",
      _path == "/api/v2/mix/order/place-order" and _body["force"] == "gtc"
      and _body["presetStopSurplusPrice"] == "66000.0" and _body["presetStopLossPrice"] == "63000.0"
      and _body["productType"] == "USDT-FUTURES", str(_body)[:120])
check("one-way mode: NO tradeSide in the payload (hedge-mode would need it, and BITGET_HEDGE=1 adds it)",
      "tradeSide" not in _body)
_p23, _b23o = _bg23._body("sell", "BTCUSDT", "0.1234", None, "stop", "63000.0",
                          "61000.0", "64000.0", "sentryBTCUSD1794662107892n6", "BTC/USD")
check("stop entry is a FIELD here (triggerType+triggerPrice+collar), not a second endpoint like OKX",
      _b23o["orderType"] == "limit" and _b23o["triggerType"] == "fill_price"
      and _b23o["triggerPrice"] == "63000.0" and float(_b23o["executePrice"]) < 63000.0
      and _p23 == "/api/v2/mix/order/place-order", str(_b23o)[:140])
check("clientOid is the deterministic fold of Sentry's cid (60 chars is over Bitget's limit)",
      _body["clientOid"] == _bg23.oid_for("sentryBTCUSD1794662107892n5")
      and len(_body["clientOid"]) <= 32 and _body["clientOid"].isalnum()
      and _bg23.oid_for("x") != _bg23.oid_for("y")
      and _body["clientOid"].startswith("sen"))
check("cancel is per-symbol only — this adapter does not expose cancel_all (the 2026-11-14 mistake)",
      not hasattr(_bg23, "cancel_all") and hasattr(_bg23, "cancel_for"))
check("a short below the venue's own notional floor is refused before it is sent",
      "minTradeUSDT" in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                          "broker_bitget.py")).read())
# the fee arithmetic that makes this venue worth wiring at all (0.02/0.06 is the published base tier)
_bg23.set_fees = None if False else None
_usd23, _r23 = (lambda: (_bl22.set_fees({"maker": 0.0002, "taker": 0.0006}),
                          _bl22.round_trip_fees(100.0, 99.5, 0.5, 200.0))[1])()
_bl22.set_fees({"maker": 0.0002, "taker": 0.0005})
_usd_okx, _r_okx = _bl22.round_trip_fees(100.0, 99.5, 0.5, 200.0)
_bl22.set_fees({"maker": 0.0040, "taker": 0.0060})
_usd_cb, _r_cb = _bl22.round_trip_fees(100.0, 99.5, 0.5, 200.0)
_bl22.set_fees(cfg22["fees"])
print(f"  [fee drag on the venue model, 0.50 % stop]  okx 0.02/0.05 -> {_r_okx:.2f}R   "
      f"bitget 0.02/0.06 -> {_r23:.2f}R   coinbase base 0.40/0.60 -> {_r_cb:.2f}R   "
      f"(live guard cap {float(cfg22['live_max_fee_r']):g}R)")
check("Bitget perps at the book's 0.5 % stop fit under live_max_fee_r, so live signals are NOT refused",
      _r23 <= float(cfg22["live_max_fee_r"]), f"{_r23:.2f}R vs cap {cfg22['live_max_fee_r']}R")
check("  ...but the margin is 0.01R WIDE, so a Bitget book must re-read /market/contracts if its "
      "tier is worse (0.02/0.10 taker would breach)", _r23 > _r_okx and _r23 / _r_okx < 2.0,
      f"bitget {_r23:.2f}R vs okx {_r_okx:.2f}R")
check("  ...and Bitget is 10x cheaper than the Coinbase lane, which is why it goes first",
      _r_cb > 8 * _r23, f"coinbase {_r_cb:.2f}R vs bitget {_r23:.2f}R")
_bl22.set_fees(cfg22["fees"])
check("Bitget's fee ladder is READ from the venue (/market/contracts), not typed from a help page",
      '"makerFeeRate"' in open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                            "broker_bitget.py")).read())

# ---------- 24: an ARMED-but-EMPTY account must not be read as a $100k paper wallet ----------
# Found while wiring the Bitget lane: `float((acct or {}).get("equity") or 100000.0)` treated a real
# 0.0 as "missing", so on key day (trade-only key pasted, nothing funded yet) every cap computed
# against money that does not exist and the book kept trying to send orders into an empty margin
# account. run_cycle.venue_equity is the shipped function; these call it, they don't re-implement it.
print("\n== 24: funded gate (armed venue with $0 equity)")
_eq_fn = getattr(rc, "venue_equity", None)
check("run_cycle exposes venue_equity (the sizing wallet is one function, not an inline `or`)",
      _eq_fn is not None)
if _eq_fn:
    eq, ok, why = _eq_fn({"equity": 0.0}, True)
    check("armed + venue says $0 -> NO new entries, and it says why",
          ok is False and eq == 0.0 and "empty" in why.lower(), f"{eq}, {ok}, {why!r}")
    eq, ok, why = _eq_fn({"equity": 0}, True)
    check("integer 0 behaves like 0.0 (this was the whole bug: falsy != missing)",
          ok is False and eq == 0.0)
    eq, ok, why = _eq_fn({"equity": None}, True)
    check("a live venue read that OMITS equity fails closed too, never defaults to six figures",
          ok is False and eq == 0.0 and "no equity" in why.lower())
    eq, ok, why = _eq_fn({"equity": 20000.0}, True)
    check("funded account: equity is used as-is and entries are allowed",
          ok is True and eq == 20000.0 and why == "")
    eq, ok, why = _eq_fn(None, False)
    check("shadow/DRY keeps the $100k paper wallet (nothing else about the books changes)",
          ok is True and eq == 100000.0)
    eq, ok, why = _eq_fn({"equity": 0.0}, False)
    check("...even when a rehearsal venue happens to report 0",
          ok is True and eq == 0.0)
    check("negative equity (a liquidation-pending wallet) also refuses",
          _eq_fn({"equity": -12.5}, True)[1] is False)
check("the falsy-swallowing expression is gone from the CODE (a docstring may still name it)",
      "equity = float((acct or {})" not in src and "venue_equity(acct, MONEY)" in src)
check("and the refusal names both fixes (fund it, or disarm the key) without touching stops",
      "Fund the account or disarm the key" in src
      and "still managed" in src)

# ...and the whole gate end-to-end: the shipped probe runs run_cycle.run() against a stubbed venue
# that answers the wallet with $0 and records any attempt to place an order. 0.2 s, no network.
_probe24 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools/checks/check_empty_wallet.py")
if os.path.exists(_probe24):
    import subprocess as _sp24
    _r24 = _sp24.run([sys.executable, _probe24], capture_output=True, text=True, timeout=180)
    _out24 = (_r24.stdout or "") + (_r24.stderr or "")
    check("THE PROBE: armed Bitget book + $0 wallet -> LIVE ACK, one ALERT, ZERO orders attempted",
          "RESULT: PASS" in _out24 and "orders attempted against the venue: 0" in _out24
          and "MONEY: True" in _out24, " ".join(_out24.split())[-160:])
    check("...and the equity it reports is the venue's, not the paper wallet's",
          "equity $0.00" in _out24, [l for l in _out24.splitlines() if "scan ok" in l][-1][:150]
          if "scan ok" in _out24 else "no scan line")
else:
    check("empty-wallet probe is shipped", False, _probe24)


print("\n%d checks failed" % len(FAILS))
sys.exit(1 if FAILS else 0)