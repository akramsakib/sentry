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

print("\n%d checks failed" % len(FAILS))
sys.exit(1 if FAILS else 0)
