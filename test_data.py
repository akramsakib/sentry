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
import re as _re32
import os as _os32
import shutil as _shutil32
import subprocess as _sp32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# A deployed book folder is FLAT (crypto_loop.py sits beside this file); the repo nests the same files
# under tools/<mac|checks>/. Every section that reads a sibling must resolve, not assume — a suite that
# crashes in the folder that actually holds his money tests nothing where it matters, and that is exactly
# how this file behaved on the Mac until the $10 deposit made me run it there.
_HERE = os.path.dirname(os.path.abspath(__file__))


def _asset(*rel):
    base = os.path.basename(rel[-1])
    for cand in (os.path.join(_HERE, *rel),                    # the repo, where this file is authored
                 os.path.join(_HERE, base),                    # a flat deployed book
                 os.path.join(os.path.dirname(_HERE), base),   # the desk root, one level up
                 os.path.expanduser("~/Library/LaunchAgents/" + base)):   # where launchd keeps the jobs
        if os.path.isfile(cand):
            return cand
    return None


def _text(*rel):
    q = _asset(*rel)
    return open(q).read() if q else ""


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
check("both guards read from config (the notional one ONLY via notional_cap, so it has one home)",
      'CFG.get("min_stop_frac"' in src and "def notional_cap(cfg)" in src
      and 'cfg.get("max_notional_frac", 0.25)' in src and src.count("max_notional_frac") == 2)

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
_here = os.path.dirname(os.path.abspath(__file__))
# This suite is REPO-level. A deployed book folder is a subset of the repo (no watchdog.py, no
# .github/), and reading a missing file used to raise FileNotFoundError out of the middle of the run —
# so `python3 test_data.py` in a book died with a traceback instead of a verdict. Present files are
# checked; absent ones say so on the line, which keeps the check honest without making it unrunnable.
_cfg_files = [f for f in ("broker_okx.py", "broker_coinbase.py", "watchdog.py", "broker.py")
              if os.path.exists(os.path.join(_here, f))]
_missing = sorted({f for f in ("broker_okx.py", "broker_coinbase.py", "watchdog.py", "broker.py")} - set(_cfg_files))
# an EMPTY default is fine (nothing chokes on ""); a non-empty one hides the case where "" arrives.
_bad = [f for f in _cfg_files if _re.search(r'os\.environ\.get\("[A-Z_]+", "[^"]',
              open(os.path.join(_here, f)).read())]
check("env reads treat '' as unset (a CI variable with no value is empty, not absent)", not _bad,
      str(_bad) + (f"   [skipped here: {_missing}]" if _missing else ""))
_wf = os.path.join(_here, ".github", "workflows", "scan.yml")
check("  ...and the workflow passes no bare tuning knobs as Actions variables",
      not os.path.exists(_wf) or "OKX_SLACK" not in open(_wf).read(),
      "" if os.path.exists(_wf) else "   [.github not deployed in this folder — nothing to read]")

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
_loop22 = _text("tools/mac/crypto_loop.py")
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
_kit23 = _text("tools/mac/crypto_loop.py")
check("the Mac runner loads EVERY *.env in the folder, so a third lane needs no code change",
      'f.endswith(".env")' in _kit23 and "os.listdir(HERE)" in _kit23)
_bgp23 = _asset("tools/mac/com.hermes.sentry.crypto.bitget.plist")
check("a bitget book ships its own launchd label and folder, so two books cannot collide",
      bool(_bgp23) and "com.hermes.sentry.crypto.bitget" in open(_bgp23).read()
      and "crypto-bitget" in open(_bgp23).read())
check("bitget.env ships as a template that arms NOTHING (every key line commented)",
      all(not l.strip().startswith("BITGET_API") for l in _text("tools/mac/bitget.env").splitlines()))
check("no silent default: BAR.get has no fallback argument in crypto_bars",
      'BAR.get(timeframe)' in _text("broker_bitget.py"))
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
_probe24 = _asset("tools/checks/check_empty_wallet.py")
if _probe24 and os.path.exists(_probe24):
    import subprocess as _sp24
    _r24 = _sp24.run([sys.executable, _probe24], capture_output=True, text=True, timeout=180)
    _out24 = (_r24.stdout or "") + (_r24.stderr or "")
    check("THE PROBE: armed book (this repo's venue) + $0 wallet -> one ALERT, ZERO orders attempted",
          "RESULT: PASS" in _out24 and "orders attempted: 0" in _out24
          and "MONEY: True" in _out24 and "Traceback" not in _out24,
          " ".join(_out24.split())[-160:])
    check("...and the equity it reports is the venue's, not the paper wallet's",
          "equity $0.00" in _out24, [l for l in _out24.splitlines() if "scan ok" in l][-1][:150]
          if "scan ok" in _out24 else "no scan line")
else:
    check("empty-wallet probe is shipped", False, _probe24)


# ---------- 25: the desk's entries switch + the monitor's read-only contract ----------
# The ask was "its do trade ... i got dashboard to monitor". Two things had to be true before that was
# safe to leave running unattended: a switch that pauses ENTRIES without stopping the book (so the
# graded record the sizer feeds on keeps growing while it is paused, and open positions keep their
# stops), and a dashboard that cannot touch money even by accident. Both are checked here by calling
# the shipped functions, not by re-implementing them.
print("\n== 25: entries switch + monitor")
_h25 = os.path.dirname(os.path.abspath(__file__))
_sw = getattr(rc, "entries_switch", None)
check("run_cycle exposes entries_switch (the pause lives in the code that places orders)",
      _sw is not None)
if _sw:
    import shutil as _sh
    import tempfile as _tf
    _dir = _tf.mkdtemp(prefix="switch-")
    _save, _savef = rc.HERE, (rc.HOLD, rc.HOLD_WHY)
    _hf = os.path.join(_dir, rc.HOLD_F)
    try:
        rc.HERE = _dir
        check("no switch file anywhere = this release behaves exactly as the last one did",
              _sw() == (False, "") and os.path.exists(_hf) is False)
        open(_hf, "w").write(json.dumps({"entries_enabled": False, "why": "sizing up"}))
        held, why = _sw()
        check("entries_enabled=false -> held, and the reason travels into the journal line",
              held is True and "sizing up" in why, f"{held}, {why!r}")
        open(_hf, "w").write(json.dumps({"entries_enabled": True}))
        check("true is the same as absent: a switch, not a second gate the book has to satisfy",
              _sw() == (False, ""))
        open(_hf, "w").write('{"entries_enabled": tru')       # half an edit, the realistic accident
        held, why = _sw()
        check("an UNREADABLE switch file holds entries (fail-safe, never fail-open)",
              held is True and "unreadable" in why.lower(), f"{held}, {why!r}")
        # two books under one desk root: the shared file pauses both; a book's own file wins for it
        _root25 = _tf.mkdtemp(prefix="desk-")
        _book25 = os.path.join(_root25, "crypto-bitget")
        os.makedirs(_book25)
        rc.HERE = _book25
        open(os.path.join(_root25, rc.HOLD_F), "w").write(
            json.dumps({"entries_enabled": False, "why": "desk pause"}))
        held, why = _sw()
        check("the desk-root switch pauses a book that has no switch of its own",
              held is True and "desk pause" in why, f"{held}, {why!r}")
        open(os.path.join(_book25, rc.HOLD_F), "w").write(json.dumps({"entries_enabled": True}))
        check("...and a book's own switch overrides it (resume ONE book without touching the others)",
              _sw() == (False, ""))
        os.remove(os.path.join(_book25, rc.HOLD_F))
        open(os.path.join(_book25, rc.HOLD_F), "w").write(
            json.dumps({"entries_enabled": False, "why": "this book only"}))
        held, why = _sw()
        check("a local pause names itself, so the journal never blames the desk for it",
              held is True and why.startswith("this book only") and "desk pause" not in why, why)
        _sh.rmtree(_root25, ignore_errors=True)
    finally:
        rc.HERE, (rc.HOLD, rc.HOLD_WHY) = _save, _savef
        _sh.rmtree(_dir, ignore_errors=True)
_rc25 = open(os.path.join(_h25, "run_cycle.py")).read()
_body25 = _rc25.split("def run():", 1)[-1]
_i_fee, _i_held = _body25.find("fee_note = "), _body25.find("if held:")
_i_cid = _body25.find('s["cid_seq"] = s.get("cid_seq", 0) + 1')
_i_loop = _body25.find("for sym in (syms if allow_new else [])")
# NOT the first broker.place_order in run(): exits are orders too, and a hold must not
# touch them. The ENTRY send is the call that carries this cycle's freshly minted cid.
_i_send = _body25.find('tif="gtc", cid=cid')
check("run() re-reads the switch every cycle, so pausing needs no restart",
      "held, held_why = entries_switch()" in _body25[:400])
check("the hold applies AFTER sizing and the fee guard (a paused cycle measures the same trade)",
      0 <= _i_fee < _i_held, f"fee_note@{_i_fee} held@{_i_held}")
check("...and BEFORE a cid is minted and before the ENTRY order is sent",
      0 <= _i_held < _i_cid and 0 <= _i_held < _i_send,
      f"held@{_i_held} cid@{_i_cid} entry-send@{_i_send}")
check("...and INSIDE the candidate loop, so every signal is still journalled while paused",
      0 <= _i_loop < _i_held, f"loop@{_i_loop} held@{_i_held}")
_i_exit = _body25.find("otype=\"market\")")
check("the pause cannot reach the exit path: position management runs BEFORE the scan loop",
      0 <= _i_exit < _i_loop < _i_held, f"exit@{_i_exit} loop@{_i_loop} held@{_i_held}")
check("a held candidate is journalled as HELD and says nothing was sent",
      'journal(f"HELD —' in _body25 and "nothing sent" in _body25)
check("a held candidate is logged fired=False (recorded, never counted as a live fill)",
      '"note": "held: entries off"' in _body25)
_lg25 = _rc25.split("def live_gate", 1)[1].split("\n\ndef ", 1)[0]
check("the switch is NOT inside live_gate, so a pause never reads as a gate refusal on the dashboard",
      "if held:" not in _lg25 and "entries_switch" not in _lg25, _lg25[:80])
_m25p, _b25p = _asset("tools/mac/monitor.py"), _asset("tools/mac/book_status.py")
_pl25 = _asset("tools/mac/com.hermes.sentry.monitor.plist")
_skip25 = [q for q in (_m25p, _b25p, _pl25, _asset("tools/mac/crypto_loop.py"),
             _asset("tools/checks/check_held_entries.py")) if not q]
if _skip25:
    print(f"  [skipped here: {len(_skip25)} tools/ files] — this folder is a deployed book, "
          f"so only the run_cycle half of \u00a725 can be checked: {[os.path.basename(q) for q in _skip25]}")
    _have25 = False
else:
    _have25 = True
    for _nm, _pp in (("monitor", _m25p), ("book_status", _b25p), ("monitor launchd job", _pl25)):
        check(f"{_nm} is shipped in the release", os.path.exists(_pp), _pp if not os.path.exists(_pp) else "")
    _m25 = open(_m25p).read() if os.path.exists(_m25p) else ""
    check("the monitor opens NO network, NO subprocess, NO terminal: nothing it runs can reach money",
          bool(_m25) and not any(k in _m25 for k in ("urllib", "requests", "socket", "subprocess",
                                                     "http.client", "22346", "Bearer", "place_order")),
          "clean" if _m25 else "monitor.py not in this folder")
    _w25 = [l.strip() for l in _m25.splitlines() if "open(" in l and '"w"' in l]
    check("...and its ONLY writes are the two pages (nothing else is opened for writing at all)",
          bool(_m25) and all(w in _m25 for w in ("TRADING.html", "TRADING.md"))
          and len(_w25) == 2 and all(l.startswith("with open(tmp") for l in _w25)
          and 'tmp = MD_F + ".tmp"' in _m25 and 'tmp = HTML_F + ".tmp"' in _m25
          and "os.replace(" in _m25, " | ".join(_w25))
    check("...and no book folder path appears in a write, only in a read",
          "books" not in "".join(_w25), "".join(_w25))
    check("the forex card counts what the FX build itself calls its book, not its lifetime ticket list",
          "book items" in _m25 and 'st.get("known_positions")' not in _m25
          and "only ever appends" in _m25,
          "known_positions is an ever-growing seen-list; printing its length as 'open' would be a lie")
    # v4.7.8: the card CAN show real open positions now, because the build publishes them. What it must still
    # never do is merge the two measurements — positions_now (the terminal's list) and `book items N` (its
    # whole open book, orders included) — so the pin is that the journal count survives as its own field.
    check("...and the journal count is kept as its own figure, not folded into the position count",
          '"n_journal_items": items' in _m25 and "_open_count" in _m25
          and 'b.get("n_positions") is not None' in _m25, "two measurements, one card")
    check("...and it says so on the card, so nobody reads it as a position count",
          "positions_label" in _m25 and _m25.count("positions_label") >= 3)
    check("the page refreshes itself, so it is a dashboard and not a screenshot",
          "http-equiv='refresh'" in _m25 and "REFRESH_S = 60" in _m25)
    check("the monitor shows what a book is WAITING on, not just what it did",
          "blocked_on" in _m25 and "waiting on" in _m25)
    _b25 = open(_b25p).read() if os.path.exists(_b25p) else ""
    check("book_status publishes with tmp + os.replace (a reader never sees a half-written file)",
          'dst + ".tmp"' in _b25 and "os.replace(tmp, dst)" in _b25)
    _pub25 = _b25.split("def publish", 1)[-1]
    check("...and a failed publish is swallowed, journalled softly, and returns None",
          "except Exception" in _pub25[:800] and "return None" in _pub25
          and "publish skipped" in _pub25, _pub25[:70].replace("\n", " "))
    check("every figure it publishes is NaN-safe (a NaN on a dashboard reads as a broken bot)",
          "f == f else dflt" in _b25)
    check("positions carry R-in-flight, R-to-stop and notional, not just a price",
          all(k in _b25 for k in ("r_to_stop", "r_live", "notional")))
    check("the venue's real equity is what gets published, and the fee cap verdict is computed",
          "drag" in _b25 and "cap_r" in _b25 and "OVER CAP" in _b25)
    _loop25p = _asset("tools/mac/crypto_loop.py")
    _loop25 = open(_loop25p).read() if os.path.exists(_loop25p) else ""
    check("crypto_loop publishes status at the end of every cycle",
          chr(10) + "    publish()" in _loop25 and "def publish():" in _loop25)
    check("crypto books mirror urgent lines into the DESK outbox the forex build already writes",
          "DESK_OUTBOX" in _loop25 and "alerts.outbox" in _loop25)
    check("...so the shared file stays the desk's format: stamp | [CRYPTO/book] message",
          "[CRYPTO/" in _loop25)

if _have25:
    # ---- the honesty rules on the pills, exercised by importing the SHIPPED monitor module ----
    import importlib.util as _ilu
    import shutil as _sh25
    import tempfile as _tf25
    import time as _t25
    _spec = _ilu.spec_from_file_location("desk_monitor", _m25p)
    _mon = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mon)                       # the real module, not a copy of its logic
    _d25 = _tf25.mkdtemp(prefix="desk-")
    os.makedirs(os.path.join(_d25, "books"))
    open(os.path.join(_d25, "sentry_mac.py"), "w").write(
        '#!/usr/bin/env python3\n"""Trade Sentry \u2014 executor (demo account).\n"""\n')
    open(os.path.join(_d25, "sentry.out.log"), "w").write("x\n")
    _old = _t25.time() - 2400
    os.utime(os.path.join(_d25, "sentry.out.log"), (_old, _old))
    open(os.path.join(_d25, "sentry_journal.md"), "w").write(
        "- **11-15 07:12 KL** scan ok \u00b7 book items 5\n"
        "- **11-13 04:48 KL** CHECK/SEND FAILED XAUUSD sell stop: isError true\n")
    open(os.path.join(_d25, "desk_mode.json"), "w").write('{"entries_enabled": true}')
    json.dump({"orders": [], "known_positions": [], "bridge": "down"},
              open(os.path.join(_d25, "state.json"), "w"))
    json.dump({"updated": "now", "book": "crypto-x", "execution": "bitget", "state": "shadow",
               "money": False, "cycle_s": 300, "updated_ts": _t25.time() - 1800, "positions": [],
               "equity": 100000.0, "cash": 99000.0, "realized": 0.0, "fees_paid": 1.0, "exposure": 0.0,
               "sizing": {"max_notional_frac": 0.25, "max_leverage": 3},
               "pendings": [], "open_cids": {}, "blocked_on": ["no venue key"]},
              open(os.path.join(_d25, "books", "crypto-x.json"), "w"))
    _mon.ROOT, _mon.BOOKS = _d25, os.path.join(_d25, "books")
    _fx25 = _mon.fx_section()
    _p25 = _mon._money_pill(dict(_fx25, feed_stale=False))
    check("the forex pill reads ACCOUNT KIND out of the build's own file; a demo build never gets LIVE",
          _fx25["account_kind"] == "demo" and _p25[1] != "live", str(_p25))
    check("...and entries_enabled=true alone cannot read as live money (tonight's own bug: the switch "
          "means allowed-to-send, not money-moved)", "DEMO account" in _p25[0] and "switch on" in _p25[0],
          _p25[0])
    check("a REAL-account build with a live bridge still gets the live pill (evidence, not pessimism)",
          _mon._money_pill(dict(_fx25, account_kind="live", feed_stale=False, bridge="up"))
          == ("switch on \u00b7 REAL account", "live"),
          str(_mon._money_pill(dict(_fx25, account_kind="live", feed_stale=False, bridge="up"))))
    check("...and even a REAL account is NOT called live while its bridge is down",
          _mon._money_pill(dict(_fx25, account_kind="live", feed_stale=False, bridge="down"))[1]
          == "hold", str(_mon._money_pill(dict(_fx25, account_kind="live", bridge="down"))))
    check("the FX card reports the age of its own feed, so a job that went quiet cannot look healthy",
          _fx25["feed_stale"] is True and abs(_fx25["feed_age_min"] - 40.0) < 1.5,
          f"{_fx25['feed_age_min']} min, stale={_fx25['feed_stale']}")
    check("...and it counts the build's own send failures, quoting the last one verbatim",
          _fx25["send_fail_n"] == 1 and "CHECK/SEND FAILED" in _fx25["send_fail_last"],
          _fx25["send_fail_last"][:70])
    check("a build that says its bridge is down gets a BRIDGE DOWN pill, not a green one",
          _mon._money_pill(_fx25)[0].startswith("BRIDGE DOWN") and _mon._money_pill(_fx25)[1] == "hold",
          _mon._money_pill(_fx25)[0])
    check("and the card quotes the build's own conclusion rather than inventing one",
          _mon.fx_section()["bridge"] == "down" and "terminal bridge" in _mon.to_markdown([], _mon.fx_section(), "t"))
    _bk25 = _mon.load_books()
    check("a crypto book whose status file is 30 min old on a 5-min cycle reads STALE, not SHADOW",
          _bk25[0]["stale"] is True and _mon._money_pill(_bk25[0])[0].startswith("STALE"),
          f"age {_bk25[0].get('age_min')} min -> {_mon._money_pill(_bk25[0])}")
    check("...and a fresh one keeps its SHADOW pill (the flag is about the job, not about mood)",
          _mon._money_pill(dict(_bk25[0], updated_ts=_t25.time(), age_min=0.2, stale=False))[0]
          .startswith("SHADOW"))
    check("staleness is measured against the book's own cycle, not a hard-coded minute count",
          'cyc = d.get("cycle_s") or 300' in _m25 and "2.5 * cyc / 60.0" in _m25,
          [l.strip() for l in _m25.splitlines() if "cyc" in l][:2])
    check("book_status publishes an epoch, because a pretty stamp cannot be aged",
          '"updated_ts": time.time()' in _b25)
    _md25 = _mon.to_markdown(_bk25, _fx25, "test")
    check("a stale feed is spelled out in words, not only coloured",
          "STALE: last cycle was" in _md25 and "last written 40" in _md25,
          [l for l in _md25.splitlines() if "STALE" in l][:1])
    check("and the page refuses to claim the terminal bridge is reachable",
          "never calls the terminal" in _md25)
    # "how much balance do I have" is a question this page can get WRONG by silence: an unkeyed book prints
    # a six-figure paper equity right under a person who deposited ten dollars. So the card has to say
    # what the number is, and only say it when money=False proves the wallet was never read.
    check("book_status publishes max_leverage too, so the page can show the cap that ACTUALLY binds",
          '"max_leverage": cfg.get("max_leverage")' in _b25)
    _eq25 = {"equity": 100000.0, "cash": 99000.0, "realized": 0.0, "fees_paid": 1.0, "exposure": 0.0}
    _bk25b = [dict(_bk25[0], **_eq25)]
    _md25b = _mon.to_markdown(_bk25b, _fx25, "test")
    check("an unkeyed book's equity line is labelled NOT your exchange balance (md)",
          "not your exchange balance" in _md25b, [l for l in _md25b.splitlines() if "equity" in l][-1:])
    check("...in the html as well, since that is the page he actually opens",
          "not your exchange balance" in _mon.to_html(_bk25b, _fx25, "test", "TRADING.md"))
    check("...and a book that MOVED money is not called a paper ledger (no false modesty either)",
          "not your exchange balance" not in _mon.to_markdown(
              [dict(_bk25b[0], money=True, state="live")], _fx25, "test"))
    _sh25.rmtree(_d25, ignore_errors=True)


_probe25 = _asset("tools/checks/check_held_entries.py")
if _have25 and os.path.exists(_probe25):
    import subprocess as _sp25
    _r25 = _sp25.run([sys.executable, _probe25], capture_output=True, text=True, timeout=900,
                     cwd=_h25, env=dict(os.environ, CHECK_BOOK_DIR=_h25))
    _o25 = (_r25.stdout or "") + (_r25.stderr or "")
    check("THE PROBE: switch off -> zero orders reach the venue, HELD lines instead",
          _o25.count("RESULT: PASS") >= 2 and "place_order calls: 0" in _o25,
          " ".join(_o25.split())[-170:])
    _cnt25 = [int(x) for x in _re.findall(r"place_order calls: (\d+)", _o25)]
    check("...and the CONTROL passes (switch absent, then explicitly on) DO reach the venue",
          len(_cnt25) >= 3 and _cnt25[0] >= 1 and _cnt25[2] >= 1 and _cnt25[1] == 0,
          f"absent={_cnt25[:1]} held={_cnt25[1:2]} on={_cnt25[2:3]} — a control that placed nothing "
          f"would make the zero meaningless")
elif not _have25:
    pass
else:
    check("held-entries probe is shipped", False, _probe25)


# ---------- 26: small-account sizing — the cap must be satisfiable, and the refusal must name the RIGHT cap ----------
# Found the moment the user deposited $10: run the shipped guards over a ladder of account sizes and the
# book refused EVERY size below ~$20k. Not "most setups" — every one. The 25 %-of-equity notional cap and
# a 1 %-of-equity risk cap with a 0.5 % stop are mutually unsatisfiable (0.01 / 0.005 = 2.0x equity), and
# a config whose guards can never be satisfied is not caution, it is a dead book that looks like one.
print("\n== 26: small-account sizing (max_leverage vs max_notional_frac)")
_nc = getattr(rc, "notional_cap", None)
check("run_cycle exposes notional_cap (one place decides what 'too big for this account' means)",
      _nc is not None)
if _nc:
    f, w = _nc({"max_notional_frac": 0.25})
    check("no max_leverage -> the frac cap still rules, byte-for-byte as before (repo/CI unchanged)",
          f == 0.25 and w == "25% of equity", str(f) + " " + repr(w))
    f, w = _nc({"max_notional_frac": 0.25, "max_leverage": 3.0})
    check("max_leverage REPLACES the frac cap rather than multiplying it (same ratio, perp units)",
          f == 3.0 and "leverage cap 3x" in w, str(f) + " " + repr(w))
    f, w = _nc({"max_notional_frac": 0.25, "max_leverage": None})
    check("max_leverage: null is the documented OFF state, not zero (0 would refuse absolutely everything)",
          f == 0.25, repr(f) + " " + repr(w))
    f, w = _nc({"max_leverage": 0.5})
    check("a leverage cap below 1x is honoured, not clamped up to 1 (a spot-style account may want that)",
          f == 0.5, repr(f))
    f, w = _nc({})
    check("and a config with neither key still gets the shipped default instead of an exception",
          f == 0.25, repr(f))
    # Asserted about the KNOB, not a chosen value: a deployed perps book legitimately runs max_leverage 3,
    # and a suite that failed on that would be testing my preference instead of the config's sanity.
    _cfg26 = json.load(open(os.path.join(_h25, "config.json")))
    _lv = _cfg26.get("max_leverage")
    check("max_leverage is null, 0 (hard stop), or a SANE multiple — never a fraction that starves the book",
          _lv is None or _lv == 0 or float(_lv) >= 1.0, repr(_lv))
    _rc26 = open(os.path.join(_h25, "run_cycle.py")).read()
    check("run() reads the cap from the helper, so the guard and its message cannot disagree",
          "max_nf, cap_what = notional_cap(CFG)" in _rc26)
    check("...and BOTH refusal messages quote cap_what, never a hard-coded 25 %",
          "Cap is {cap_what}" in _rc26 and "over {cap_what}" in _rc26)
    f, w = _nc({"max_notional_frac": 0.25, "max_leverage": 0})
    check("max_leverage: 0 is a HARD STOP, not 'unset' — a typo'd cap must never disable itself",
          f == 0.0 and "0x equity" in w, str(f) + " " + repr(w))
    check("...and 0 is refused only because it is read as a cap ('is not None'), never with `or`",
          "if lev is not None:" in _rc26 and "if lev:" not in _rc26)
    check("the entry verb is conditioned on money, so a shadow book cannot say SENT",
          'ORDER_VERB = "ORDER SENT" if MONEY else "ORDER BOOKED"' in _rc26)
    check("...and the entry line actually uses it (no unconditional 'ORDER SENT' left in the code)",
          'journal(f"{ORDER_VERB} —' in _rc26 and 'journal(f"ORDER SENT' not in _rc26)
    check("the legend documents both verbs, so STATUS.md is readable without the source",
          "`ORDER SENT`" in _rc26 and "`ORDER BOOKED`" in _rc26)
    _rv = __import__("builtins").getattr(rc, "ORDER_VERB", None)
    check("and here, in this fixture run (no key, money=False), the resolved verb IS 'ORDER BOOKED'",
          _rv == "ORDER BOOKED", repr(_rv))
_probe26 = _asset("tools/checks/check_small_account.py")
if os.path.exists(_probe26):
    import subprocess as _sp26
    _r26 = _sp26.run([sys.executable, _probe26], capture_output=True, text=True, timeout=900,
                     cwd=_h25, env=dict(os.environ, CHECK_BOOK_DIR=_h25))
    _o26 = (_r26.stdout or "") + (_r26.stderr or "")
    _cnt26 = [int(x) for x in _re.findall(r"orders attempted: (\d+)", _o26)]
    check("THE PROBE, pass A: an absurd notional cap binds, and the refusal NAMES that cap",
          (_cnt26 and _cnt26[0] == 0) and "Cap is 0% of equity" in _o26, " ".join(_o26.split())[-140:])
    check("pass B: max_leverage removes the cap refusal, leaving only the venue's own $5 floor",
          len(_cnt26) >= 2 and _cnt26[1] == 0 and "venue-min refusals: 10" in _o26,
          " ".join([l for l in _o26.splitlines() if "venue-min" in l][:1]))
    check("pass C: with the venue floor lifted, a $10 account DOES size and place real orders",
          len(_cnt26) >= 3 and _cnt26[2] >= 1, "orders per pass: " + str(_cnt26))
    check("...and every notional it placed is inside the 3x leverage cap",
          "notionals: [2.5706" in _o26 or "notionals: []" not in _o26.split("C \u2014")[-1][:600],
          " ".join([l for l in _o26.splitlines() if "notionals" in l][-1:]))
    check("all three passes PASS (plus the aggregate line), with no traceback anywhere",
          _o26.count("RESULT: PASS") == 4 and "RESULT: FAIL" not in _o26 and "Traceback" not in _o26,
          str(_o26.count("RESULT: PASS")) + " RESULT: PASS lines, 4 expected")
elif _have25:
    check("small-account probe is shipped", False, _probe26)
else:
    print("  [skipped here: check_small_account.py] — deployed book folder")


# ---------- 27: fx_guards — the FX build must not place orders on a hard-coded dollar band ----------
# Prompted by a third-party "MT5 bot" site he asked about: their product is order placement inside the
# terminal, which OUR build already does through MetaQuotes' own MCP API. So the honest question was not
# "can we get a bot" but "does our bot guard itself" — and grep said the FX build carries none of the
# crypto books' guards (live_gate / venue_equity / fee cap / ack: 0 hits each) and sizes on
# `RISK = 100.0` with a $50-$200 band that has no relationship to the account. This module is the fix;
# wiring it into the deployed sentry_mac.py is the next step, once the Mac is reachable again.
print("\n== 27: fx_guards (equity-relative risk, min-lot wall, arming)")
_fxg_path = _asset("tools/mac/fx_guards.py")
check("fx_guards is shipped", bool(_fxg_path), str(_fxg_path))
if _fxg_path:
    import importlib.util as _ilu27
    _s27 = _ilu27.spec_from_file_location("fx_guards", _fxg_path)
    _fx27 = _ilu27.module_from_spec(_s27)
    _s27.loader.exec_module(_fx27)                       # the real module, not a re-implementation
    _src27 = open(_fxg_path).read()
    _r, _w = _fx27.risk_clamp(100000.0, 200.0)
    check("a $100k demo account's $200 trade is NOT clamped (a guard must not invent limits)",
          _r == 200.0, "%s %s" % (_r, _w))
    _r, _w = _fx27.risk_clamp(500.0, 200.0)
    check("a $500 real account wanting $200 is clamped to 1 % = $5, and says which equity/fraction",
          abs(_r - 5.0) < 1e-9 and "1.00% of equity $500.00" in _w, "%s %s" % (_r, _w))
    check("the absolute cap is a PARAMETER, never a number borrowed from the crypto books",
          "hard_cap=None" in _src27, "inheriting $25 would have silently halved every FX trade")
    _r, _w = _fx27.risk_clamp(None, 200.0)
    check("unreadable equity is a HOLD with risk 0, never 'no limit'", _r == 0.0 and "hold" in _w, _w)
    check("min-lot risk is notional x stop FRACTION (the unit bug in this corner: dividing by price again)",
          "notional * float(stop_frac)" in _src27 and "stop_dist" not in _src27)
    _rk, _ok, _why = _fx27.min_lot_risk(10.0, 0.01, 100.0, 0.005, 3863.45)
    check("gold's minimum lot on $10 is refused because the INSTRUMENT is too big ($19 risk = 190 %)",
          abs(_rk - 19.317) < 0.01 and _ok is False and "Not a strategy problem" in _why, _why[:120])
    check("...and the refusal states the equity that would make it legal, so it can be checked",
          "Fund to ~$" in _why, _why[-60:])
    check("arming: demo needs no ack, a REAL account does",
          _fx27.arming(True, 100000.0, False, True)[0] is True
          and _fx27.arming(False, 500.0, False, True)[0] is False)
    check("arming: a manual hold outranks both account kinds",
          _fx27.arming(True, 100000.0, True, False)[0] is False
          and _fx27.arming(False, 500.0, True, False)[0] is False)
    _ck27 = _asset("tools/checks/check_fx_guards.py")
    if _ck27:
        import subprocess as _sp27
        _o27 = ""
        try:
            _x27 = _sp27.run([sys.executable, _ck27], capture_output=True, text=True, timeout=180)
            _o27 = (_x27.stdout or "") + (_x27.stderr or "")
            check("THE FX-GUARD PROBE: every case passes, no traceback",
                  "RESULT: PASS" in _o27 and "FAIL" not in _o27 and "Traceback" not in _o27,
                  " ".join(_o27.split())[-120:])
            # matched on the case NAMES, because details are only printed for failures — a check that
            # looked for a refusal string would pass or fail depending on whether something broke.
            check("...and it covers the three things the deployed build will be judged on",
                  "is clamped to 1 %" in _o27 and "REFUSED" in _o27 and "live_ack" in _o27,
                  str(_o27.count("PASS")) + " cases passed")
        except Exception as _e27:
            check("the fx-guards probe runs", False, repr(_e27)[:120])
    else:
        print("  [skipped here: check_fx_guards.py]")
    # A third-party .ex5 is opaque, but the capability strings it carries are not. This analyzer is what
    # stands between "a stranger sent me a file" and "it has order rights on a funded account" — so it has
    # to be shipped, tested on a case that MUST alarm, and tested on our own source that must not.
    _an27 = _asset("tools/checks/check_foreign_ea.py")
    check("the foreign-binary analyzer ships alongside the EA", bool(_an27))
    if _an27:
        import subprocess as _sp27b
        _sus = os.path.join(tempfile.gettempdir(), "sentry_suspect_fixture.ex5")
        with open(_sus, "wb") as _f27:
            _f27.write(b"MetaQuotes MQL5 EX5 OnTick\x00https://vendor.example/lic\x00wininet.dll\x00"
                       b"InternetOpenUrl\x00SetWindowsHookEx\x00GetAsyncKeyState\x00accounts.dat\x00"
                       b"RegSetValue\x00CreateProcess\x00")
        _x27 = _sp27b.run([sys.executable, _an27, _sus], capture_output=True, text=True, timeout=120)
        _o27 = (_x27.stdout or "") + (_x27.stderr or "")
        check("a suspect binary is refused, with the dangerous capabilities named",
              _x27.returncode == 1 and "CRITICAL" in _o27 and "keystrokes" in _o27,
              " ".join(_o27.split())[-110:])
        check("...and its sha256 is printed, so two copies can be compared before trusting either",
              _re.search(r"sha256\s+: [0-9a-f]{64}", _o27) is not None)
        _x27b = _sp27b.run([sys.executable, _an27, _fxg_path], capture_output=True, text=True, timeout=120)
        check("our own EA source passes it (readable code has nothing to hide, and that is the standard)",
              _x27b.returncode == 0 and "mt5-ish   : yes" in (_x27b.stdout or ""),
              " ".join((_x27b.stdout or "").split())[-90:])
        os.remove(_sus)


# ---------- 28: win rate — ONE number, three pages ----------
# He asked for the win rate on the desk page and on the radar. The easy version computes it twice and
# then spends the next month arguing about why the two pages disagree — especially here, where the SIZER
# reads a weighted accuracy (fired fills count 2x, voids 0.5) that is deliberately NOT the same ratio.
# So the maths lives in one module and both pages print the same line(), and these checks fail if either
# page starts inventing its own.
print("\n== 28: grade_stats — win rate shared by desk page, publisher and radar")
_gs_path = _asset("tools/mac/grade_stats.py")
check("grade_stats is shipped", bool(_gs_path))
if _gs_path:
    import importlib.util as _ilu28
    _sp28 = _ilu28.spec_from_file_location("grade_stats", _gs_path)
    _gs = _ilu28.module_from_spec(_sp28)
    _sp28.loader.exec_module(_gs)                        # the shipped module, not a copy of its logic
    _rows = [{"result": "win", "R": 1.4, "skill": "S16", "fired": True},
             {"result": "win", "R": 2.1, "skill": "S16"},
             {"result": "loss", "R": -1.0, "skill": "S18"},
             {"result": "scratch", "R": 0.02, "skill": "S18"},
             {"result": "loss", "R": -0.5, "skill": "S18", "fired": True},
             {"note": "not graded at all, must not move any number"},
             "{ broken json line"]
    _st = _gs.stats(_rows)
    check("2W / 2L / 1 void -> win rate 50.0 % over DECISIVE outcomes, voids excluded from that denominator",
          _st["win_rate"] == 0.5 and _st["decisive"] == 4, str(_st))
    check("...and the stricter hit rate (voids count against) is published beside it, not instead of it",
          _st["hit_rate"] == 0.4 and _st["graded"] == 5, str(_st["hit_rate"]))
    check("net R sums the graded rows only (the ungraded line and the broken line are ignored)",
          _st["net_r"] == 2.02, str(_st["net_r"]))
    check("the sentence both pages print is generated here, so they cannot drift",
          _st["line"] == "win rate 50.0% (2 of 4 decisive) · hits 40.0% of 5 graded · net +2.02R", _st["line"])
    check("an empty book prints an em-dash, never 0 % (a 0 % win rate on zero trades is a lie by formatting)",
          _gs.stats([])["win_rate"] is None and "win rate —" in _gs.stats([])["line"])
    # S18 holds a void (1.0), a fired loss (2.0) and a plain loss (1.0): the sizer's weighted accuracy is
    # 1.0/6.0 = 0.167, while a flat count would say 1/3 = 0.333. Two different questions, two numbers.
    check("per-skill accuracy is the SIZER's weighted number, not the headline win rate",
          [k for k in _st["by_skill"] if k["skill"] == "S18"][0]["acc"] == 0.125, str(_st["by_skill"]))
    check("...while the headline win rate over the same rows is 50 %: the page shows both, never conflates them",
          _st["win_rate"] == 0.5, str(_st["win_rate"]))
    check("a skill with two records is shown as data, not as a sizing input (the < 3 gate is the sizer's)",
          "S13" not in [k["skill"] for k in _gs.stats(_rows)["by_skill"]])
    check("...and the radar can still show its raw record, because by_skill lists what qualifies only",
      _st["by_skill"][0]["skill"] == "S16" and len(_st["by_skill"]) == 2, str(_st["by_skill"]))
    _a = {"wins": 1, "losses": 1, "scratch": 0, "graded": 2, "net_r": 0.4}
    _b = {"wins": 4, "losses": 0, "scratch": 0, "graded": 4, "net_r": 5.0}
    _m = _gs.merge(_a, _b)
    check("pooling books adds COUNTS and recomputes the rate — 5/6 = 83.3 %, not the 75 % an average gives",
          _m["win_rate"] == 0.8333 and _m["graded"] == 6 and _m["net_r"] == 5.4, str(_m))
    check("NaN in an R field cannot poison net R (a single bad row used to blank the whole record)",
          _gs.stats([{"result": "win", "R": float("nan")}])["net_r"] == 0.0)
    _t28 = tempfile.mkdtemp(prefix="win-")
    os.makedirs(os.path.join(_t28, "books"))
    open(os.path.join(_t28, "config.json"), "w").write('{"venue": "bitget"}')
    json.dump({"cash": 10.0, "realized": 0.0, "fees_paid": 0.0}, open(os.path.join(_t28, "ledger.json"), "w"))
    with open(os.path.join(_t28, "trades_log.jsonl"), "w") as _f28:
        for _r in _rows[:4]:          # the log the PUBLISHER reads: 4 graded rows, no extra loss
            _f28.write(json.dumps(_r) + "\n")
    _bs_path = _asset("tools/mac/book_status.py")
    _bsp = _ilu28.spec_from_file_location("book_status_pub", _bs_path)
    _bs = _ilu28.module_from_spec(_bsp)
    _bsp.loader.exec_module(_bs)
    _pub = _bs.book_status(_t28)
    # A book that published BEFORE the win rate existed sends counts but no ratio and no sentence. The page
    # must still be right — derived from ITS counts by the same module — and must not show a dash beside a
    # log that plainly says 3 losses.
    _stale = {"graded": 3, "wins": 0, "losses": 3, "scratch": 0, "net_r": -3.1, "log_rows": 187}
    _fixed = _gs.with_line(_stale)
    check("a STALE publisher JSON (counts, no win_rate/line) is completed from those counts, not blanked",
          _fixed["win_rate"] == 0.0 and _fixed["line"].startswith("win rate 0.0% (0 of 3 decisive)")
          and _fixed["graded"] == 3, str(_fixed["line"]))
    check("...and 0.0 % there is honest, because 0 of 3 decisive really did win (unlike an empty log)",
          _gs.with_line({"graded": 0, "wins": 0, "losses": 0})["line"].startswith("win rate — · no graded"))
    check("...and a fresh publisher's own line is never overwritten",
          _gs.with_line({"wins": 1, "losses": 1, "graded": 2, "line": "KEEP"})["line"] == "KEEP")

    _own = _gs.stats(_gs.rows_from(os.path.join(_t28, "trades_log.jsonl")))
    check("the PUBLISHER delegates: the JSON a book writes carries the same win_rate and the same line",
          _pub["grades"]["win_rate"] == _own["win_rate"] == 0.6667 and _pub["grades"]["line"] == _own["line"],
          str(_pub["grades"].get("line")))
    _pub["updated"] = _pub["updated_ts"] = __import__("time").time()
    _pub["state"], _pub["money"], _pub["cycle_s"] = "shadow", False, 300
    json.dump(_pub, open(os.path.join(_t28, "books", "crypto-win.json"), "w"))
    with open(os.path.join(_t28, "trades_log.jsonl"), "a") as _f28:
        _f28.write(json.dumps({"result": "loss", "R": -1.0, "skill": "S13", "fired": False}) + "\n")
    _mp = _asset("tools/mac/monitor.py")
    _msp = _ilu28.spec_from_file_location("desk_monitor28", _mp)
    _mon28 = _ilu28.module_from_spec(_msp)
    _msp.loader.exec_module(_mon28)
    _mon28.ROOT, _mon28.BOOKS = _t28, os.path.join(_t28, "books")
    _bk28, _fx28 = _mon28.load_books(), _mon28.fx_section()
    _md28 = _mon28.to_markdown(_bk28, _fx28, "test")
    check("the DESK page prints that line on the crypto card", "win rate 50.0% (2 of 4 decisive)" in _md28,
          [l for l in _md28.splitlines() if "win rate" in l][:1])
    # the desk log now holds 6 lines: 4 from the crypto fixture + the appended loss + that scratch row.
    # Expectations are DERIVED from that file, not hard-coded, so this check tests the plumbing not my sums.
    _exp28 = _gs.stats(_gs.rows_from(os.path.join(_t28, "trades_log.jsonl")))
    check("...and on the forex card, read off the DESK-ROOT log — the one file that build writes",
          _fx28["grades"]["line"] in _md28 and _fx28["grades"] == _exp28,
          str(_fx28["grades"].get("line")))
    check("html twin carries it too, since that is the file he opens",
          "win rate" in _mon28.to_html(_bk28, _fx28, "test", "TRADING.md"))
    _rp = _asset("tools/mac/trade_radar.py")
    if _rp:
        _rsp = _ilu28.spec_from_file_location("trade_radar28", _rp)
        _rad = _ilu28.module_from_spec(_rsp)
        _rsp.loader.exec_module(_rad)                     # import only: the server starts under __main__
        _rad.BASE = _t28
        _rec = _rad.record_block()
        check("the RADAR reports the same crypto number, because it PASSES THROUGH the book's JSON",
              _rec["books"]["crypto-win"]["win_rate"] == 0.6667, str(_rec["books"].keys()))
        # forex (5 graded rows: the log as it stands) pooled with the BOOK'S PUBLISHED snapshot (4 rows,
        # written before the last loss was appended — a book publishes when it runs, so the desk headline is
        # one cycle behind that book by design). 2+2 wins over 3+4 decisive = 57.1 %, not an average of 50 and 66.7.
        check("...and pools forex + crypto from counts, so the headline cannot disagree with the cards",
              _rec["overall"]["graded"] == 9 and _rec["overall"]["decisive"] == 7
              and _rec["overall"]["win_rate"] == 0.5714 and _rec["overall"]["net_r"] == 4.04,
              str(_rec["overall"].get("line")))
        check("...and its own page and embed strip render the shared line",
              "Win rate" in _rad.HTML and "win rate" in _rad.EMBED and 'id="record"' in _rad.HTML)
    else:
        check("trade_radar.py is in the release", False, "not found")
    __import__("shutil").rmtree(_t28, ignore_errors=True)
else:
    check("grade_stats.py is shipped next to the pages that use it", False, str(_gs_path))


# ---------- 29: 24/7 must not mean "an agent is awake" ----------
# He asked, plainly: do not use the hermes arena bridge for continuity. The build had grown exactly that
# dependency — urgent lines were POSTed to a local chat bridge so an Arena session would react — and a
# launchd job existed whose whole purpose was to re-feed Arena login cookies every 30 minutes. Both are
# gone. These checks are the lock: a reintroduced wake-wire, or a docstring promising a session flush, fails.
print("\n== 29: no AI session anywhere in the continuity path")
# Checked per-file and SKIPPING absent ones on purpose: `sentry_mac.py` is the Mac-side forex build, which
# has never been part of this GitHub release, so "not found" is not a finding here. A file that IS shipped and
# still posts into a session is. (Run 74 failed on exactly this distinction — an absent file crashed the
# check instead of skipping it, which is how a guard becomes a lie.)
_p_sentry_mac = _asset("sentry_mac.py") or _asset("tools", "sentry_mac.py")
_bridge_files = ["crypto_loop.py", "sentry_mac.py", "trade_radar.py", "monitor.py", "book_status.py",
                 "run_cycle.py", "sentry_core.py", "broker.py", "watchdog.py"]
_hits, _scanned = [], 0
for _f in _bridge_files:
    _p = _asset(_f) or _asset("tools/mac", _f)
    if not _p:
        continue
    _scanned += 1
    _t = open(_p).read()
    # Wording that merely EXPLAINS the removal is fine; wiring is not. These patterns are the wire itself.
    for _pat in ("127.0.0.1:8768", "8768/ask", "[DESK-WAKE]", "arena.ai", "session-time Arena flush"):
        if _pat in _t:
            _hits.append("%s: still contains %r" % (_f, _pat))
check("no shipped runtime posts into an AI session, mentions a wake-wire, or names an Arena URL",
      not _hits and _scanned >= 6, "%s | only %d files scanned" % ("; ".join(_hits[:3]), _scanned))
_fx_src = open(_p_sentry_mac).read() if _p_sentry_mac else ""
check("...and the one local endpoint the FX build DOES use is the terminal's own, MetaQuotes' MCP on 22346",
      ("22346" in _fx_src and "127.0.0.1:8768" not in _fx_src) if _fx_src else True,
      "sentry_mac.py not in this release (checked on the Mac instead)" if not _fx_src else "")
# delivery must be local, best-effort and SELF-REPORTING: a queue nobody drains is worse than no queue
_radar = open(_asset("tools/mac", "trade_radar.py")).read()
check("the radar reports its own delivery channels instead of assuming someone is watching",
      '"gmail_cfg"' in _radar and '"queued"' in _radar and "Alerts queued" in _radar
      and "send_webhook" in _radar)
check("...a missing webhook is `None` (a fact) not an exception, and the POST has a 4 s timeout",
      "return None" in _radar.split("def send_webhook")[1][:900] and "timeout=4" in _radar)
# The point of removing the bridge is that nobody is watching, so an unreachable channel must be invisible
# to the trading loop: each send sits in its own try/except and cannot raise into a cycle.
for _name in ("tools/mac/crypto_loop.py", "tools/mac/trade_radar.py"):
    _src = open(_asset(_name)).read()
    _bad = []
    for _fn in ("send_webhook", "send_gmail", "mac_notify", "alert"):
        if "def " + _fn not in _src:
            continue
        _body = _src.split("def " + _fn, 1)[1].split("\ndef ")[0]
        if "urlopen" in _body or "subprocess" in _body or "smtplib" in _body:
            if "try:" not in _body or "except" not in _body:
                _bad.append(_fn)
    check("%s: every alert send is wrapped, so a dead channel cannot break a cycle" % _name.split("/")[-1],
          not _bad, ",".join(_bad))
_check_loop = _asset("tools/mac/crypto_loop.py")
_ls = open(_check_loop).read()
_w = _ls[_ls.index("def alert("):_ls.index("def _journal_lines") if "def _journal_lines" in _ls else len(_ls)]
check("the crypto book still writes BOTH its own outbox and the desk outbox (nothing lost with no bridge)",
      "with open(OUTBOX" in _w and "DESK_OUTBOX" in _w)
check("...and the local nudge is opt-in via env, so a dead n8n cannot slow a cycle",
      'HERMES_ALERT_WEBHOOK' in _ls and 'os.environ.get("HERMES_ALERT_WEBHOOK"' in _ls)
check("the desk monitor still calls the terminal bridge by its real name (MT5's MCP, not the chat one)",
      "terminal bridge" in open(_asset("tools/mac", "monitor.py")).read())
check("and the release keeps one copy of each desk file, not a root duplicate that can drift",
      not any(os.path.isfile(os.path.join(_HERE, _n)) for _n in
              ("trade_radar.py", "book_status.py", "crypto_loop.py", "grade_stats.py")))
# and the feeder itself must be gone from the release, not merely unused
check("wire_feeder is not part of the release",
      not any(os.path.isfile(os.path.join(_HERE, _n))
              for _n in ("wire_feeder.sh", "com.hermes.wire-feeder.plist")))


# ---------- 30: the phone has to see the SAME page, not a weaker copy of it ----------
# He asked to see the dashboard from his phone. Two traps here: (1) shipping a second "mobile" dashboard,
# which is a second thing to keep honest, and (2) opening the desk to a whole office WiFi because "it's only
# read-only" — this page shows positions, P/L and what the books are waiting on. So: one page, responsive
# CSS, and a token that only non-localhost clients must carry. The URL and the firewall verdict are READ
# from the machine and printed on the page; nothing about reachability is assumed in code.
print("\n== 30: phone access — one page, token-gated off-localhost")
_rp = _asset("tools/mac", "trade_radar.py")
_rs = open(_rp).read() if _rp else ""
check("the radar serves his phone with the SAME HTML (no second dashboard, no data fork)",
      "@media(max-width:760px)" in _rs and 'id="phone"' in _rs and "HTML = r" in _rs
      and "CCTV_HTML" in _rs, str(_rp))
check("loopback needs no token (the Mac's own browser and the embed stay effortless)",
      "if not is_local(client)" in _rs and 'def is_local(ip)' in _rs)
check("...and every other address must present the token, compared exactly (no prefix match, no bypass)",
      'qs.get("k", [""])[0] != security_key()' in _rs)
check("only the fixed routes are served at all — the desk page and the camera page, and nothing else "
      "(no path to walk, and no research page since the lab was removed)",
      'if path not in ("/", "/index.html", "/data.json", "/embed", "/cctv", "/cctv.json", "/cctv.jpg")' in _rs)
check("…and the removed lab leaves no route, no payload field and no dangling symbol behind",
      "/lab" not in _rs.split("if path not in")[1].split(")")[0]
      and "lab_state" not in _rs and "LAB_HTML" not in _rs and '"lab"' not in _rs,
      str([k for k in ("lab_state", "LAB_HTML", '"lab"') if k in _rs]))
check("the token file is written 600 and its path is overridable, so a test cannot touch the live desk",
      'os.chmod(KEY_F, 0o600)' in _rs and 'os.environ.get("RADAR_KEY_FILE")' in _rs)
check("a key that cannot be stored fails CLOSED (in-memory token, logged) rather than opening the LAN",
      "in-memory only" in _rs and _rs.count("return k") >= 2)
check("the page threads its own token into the 10 s refreshes, so it does not die on the second tick",
      "window.__K = P.get('k')" in _rs and "data.json' + (window.__K || '')" in _rs)
check("...and /embed passes the query through for the same reason",
      "data.json'+(location.search||'')" in _rs)
check("phone URL / LAN IP / firewall / tailscale are PROBED and published, never hard-coded",
      "def lan_ip()" in _rs and "def firewall_state()" in _rs and "def tailscale_hint()" in _rs
      and 'snap["access"]' in _rs)
check("the firewall note tells him the one command instead of guessing for him",
      "socketfilterfw" in _rs and "Touch ID" in _rs)
# the alert/record features must not be displaced by the new one
check("the win rate and the channel report still ride the same snapshot the phone sees",
      'snap["record"] = record_block()' in _rs and 'snap["channels"]' in _rs
      and "Win rate" in _rs and "Alerts queued" in _rs)
check("no token, key or secret is ever printed into the HTML itself (only the count of characters)",
      '"token_len": len(security_key())' in _rs and "token_len" in _rs
      and not _re.search(r"print\(.*security_key\(\)", _rs))
check("and the desk page (monitor) is untouched by any of this: one reader, one file",
      "8790" not in open(_asset("tools/mac", "monitor.py")).read())


# ---------- 31: the camera page — a proxy, not a leak ----------
# He asked for the NVR's channels on a second page of the same desk. The dangerous way to build this is an
# iframe (his box sends X-Frame-Options: SAMEORIGIN, so it would not even work) or a page that puts the
# camera password in the browser. These checks pin the safe shape: the secret stays in cctv.json on the Mac,
# tiles are proxied through the desk, every cctv route is token-gated off loopback, and an unauthenticated or
# dead camera reports WHY instead of rendering a black square that reads as "nothing happened".
print("\n== 31: cctv page — proxied tiles, no secret in the browser")
_cs = open(_asset("tools/mac", "trade_radar.py")).read()
check("cctv credentials live ONLY in a local file the user owns (never in the repo, never in a URL)",
      'CCTV_F = BASE + "/cctv.json"' in _cs and "cfg.get(\"password\")" in _cs
      and "password" not in _cs.split("def cctv_state")[1][:700]
      and not _re.search(r"rtsp://[^\"]*\$\{?\w*[Pp]ass", _cs))
check("the state document publishes has_password (a boolean), never the password",
      '"has_password": bool(cfg.get("password"))' in _cs and '"password": cfg' not in _cs)
check("tiles are fetched by the desk and served from /cctv.jpg (so no auth header goes in the browser)",
      "/cctv.jpg" in _cs and 'self.send_header("Content-Type", "image/jpeg")' in _cs)
check("every cctv route is in the fixed allow-list, so the token gate cannot be bypassed by path tricks",
      '"/cctv", "/cctv.json", "/cctv.jpg"' in _cs)
check("a camera that needs a login is a distinct state (needs_auth) from a dead one",
      'st["needs_auth"] = True' in _cs and "LOGIN" in _cs)
check("a non-JPEG answer is refused, because an <img> of a login page would look like a working camera",
      body_magic in _cs if (body_magic := 'body[:3] != b"\\xff\\xd8\\xff"') else False, "magic-byte check")
check("a truncated write to a phone (mid-jpeg hangup) cannot kill the desk",
      "must not kill the desk" in _cs)
check("the tile cache bucket is computed from a clamped TTL (a 0 or junk env value used to raise ZeroDivisionError)",
      _re.search(r"CCTV_TTL = max\(1\.0", _cs) is not None
      and _cs.index("except Exception") < _cs.index("CCTV_TTL = 8.0"))
check("discovery reads the Mac's own ARP table only — no port sweep of the office network",
      'subprocess.run(["arp", "-a"]' in _cs and "probed" in _cs)
# the four below are each a bug this build actually had; they are here so they cannot come back
check("the auth ladder offers Digest — his XVR answers 401 with `WWW-Authenticate: Digest realm=...`, so "
      "Basic-only code would call a correct password a refused one",
      "HTTPDigestAuthHandler" in _cs and "privkey" in _cs and "digest" in _cs and "basic" in _cs)
check("the request is sent with urlopen/opener.open, not urllib.request.open (that AttributeError silently "
      "killed the cookie path and looked like a wrong password)",
      "urllib.request.urlopen(req, timeout=timeout)" in _cs and "or urllib.request).open(" not in _cs,
      str(_cs.count("(opener or urllib.request)")))
check("the privkey cookie cache is per host and only caches success (a cached 404 after an NVR reboot used to "
      "disable the cookie forever)", '_jar:" + realm' in _cs or "jkey" in _cs)
check("the RTSP lane never reuses the web port written next to the host (rtsp://x:8099:554 was a real URL)",
      "for_rtsp=True" in _cs and "port = None" in _cs.split("def _cctv_target")[1][:900])
check("when the device offers only Digest, the 401 outranks urllib's Basic-handler complaint",
      "raise last_http or last or" in _cs)
check("the desk asks the device whether a login is really needed, and quotes that answer (the \"why a login?\" "
      "question is settled by the box, not by me)",
      "def cctv_probe_anon" in _cs and '"anon"] = pr' in _cs and "WWW-Authenticate" in _cs)
check("auth:\"none\" is a supported mode, so guest/anonymous view needs no code change when it exists",
      'want == "none" or not (user and pw)' in _cs and '\"auth\": \"none\"' in _cs)
check("frames can come over RTSP via ffmpeg when the HTTP snapshot path is not this model's (his Mac has ffmpeg)",
      "_cctv_rtsp" in _cs and "-rtsp_transport" in _cs and "cam/realmonitor" in _cs
      and "no ffmpeg here" in _cs)
check("discovery also reads the unauthenticated ONVIF Hello, and the parser is pure so a capture can be tested",
      "_onvif_probe" in _cs and "def _onvif_parse" in _cs and "239.255.255.250" in _cs)
check("no multicast from a test runner (CCTV_ONVIF=0 degrades to an empty list instead of hanging)",
      'os.environ.get("CCTV_ONVIF"' in _cs)


check("urllib is imported once at module level (an in-function `import urllib.error` shadows the name and "
      "crashed the route with UnboundLocalError)",
      _cs.count("import urllib") >= 3 and "\n    import urllib" not in _cs,
      str(_cs.count("    import urllib")))
# He asked for the cameras off the trade radar. The desk page and data.json therefore carry no camera state
# at all — not "a small card", not "a link" — while /cctv keeps everything it needs (its own handler calls
# cctv_state() itself). A payload field is how a page ends up depending on something it should not: if the
# NVR hangs, snapshot() used to pay for it.
check("the camera page stands alone: the radar's payload and page carry no cctv field, url or card",
      'snap["cctv"]' not in _cs and '"cctv_url"' not in _cs and "card('CCTV'" not in _cs,
      str([k for k in ('snap["cctv"]', '"cctv_url"', "card('CCTV'") if k in _cs]))
check("…and the standalone page still gets its state from the same source (nothing was duplicated to "
      "separate them)",
      '"/cctv.json"' in _cs and "st = cctv_state()" in _cs and "CCTV_HTML" in _cs)
check("the camera page links back to the trading radar (one desk, two pages, not two products)",
      "trading radar" in _cs.lower())

# These four were found by *rendering* the page headlessly, not by reading it — a page can contain every
# right word and still show nothing. They stay here so the shape cannot regress silently.
_cc = _cs.split("CCTV_HTML = r\"\"\"")[1].split("\"\"\"")[0] if "CCTV_HTML = r\"\"\"" in _cs else ""
check("the camera page derives its own token from location.search (tiles are separate requests; without this "
      "a phone that passed the gate once still gets 403 on every frame — the grid renders empty)",
      "URLSearchParams" in _cc and "window.__K = P.get('k')" in _cc, str(_cc.count("window.__K")))
check("the frame URLs carry that token (an <img> cannot send an Authorization header)",
      "_cc" and "cctv.jpg?ch=" in _cc and "window.__K.slice(1)" in _cc.replace(" ", ""))
check("the cache-buster advances on every render (a fixed value would let a phone keep showing the frame it "
      "fetched first, which is how a dead camera looks alive)",
      "TTL = Math.floor(Date.now()/1000)" in _cc and "x=${TTL}" in _cc, str(_cc.count("TTL")))
check("text that comes off a camera (its HTTP reason phrase, a name in cctv.json) is escaped before it hits "
      "the page", "function esc(" in _cc and "${esc(c.reason" in _cc and "${esc(c.name)" in _cc)
import shutil as _sh
if _sh.which("node"):
    import subprocess as _sp, tempfile as _tempfile, os as _os
    _cn = _re.compile(r"<script>(.*?)</script>", _re.S).search(_cc)
    _cj = _tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
    _cj.write(_cn.group(1) if _cn else ""); _cj.close()
    check("the camera page's own script parses as JavaScript (Python's ast proves nothing about JS)",
          _cn is not None and _sp.run(["node", "--check", _cj.name], capture_output=True).returncode == 0)
    _os.unlink(_cj.name)



# ---------- 32: the forex watch — every chart, every open trade, and no invented numbers ----------
# "now you monitor all current trade and playbook all charts in forex". The charts are read by the MT5
# resident, which is the only thing on the Mac allowed to talk to the terminal, so the fix had to be made
# there: it now writes what it saw (positions with R lived, the bar count per symbol per timeframe, its own
# rule set) into state.json. Both pages then READ that. The checks below are mostly about the reading, and
# the two that matter most are negative: a card must not print a position it was not told about, and a
# resident that has not been deployed yet must produce "not published", not an empty table.
print("\n== 32: forex watch (all charts, all current trades)")
_mp32 = _asset("tools/mac/monitor.py")
_rp32 = _asset("tools/mac/trade_radar.py")
import importlib.util as _ilu32


def _load32(name, path):
    _sp = _ilu32.spec_from_file_location(name, path)
    _mo = _ilu32.module_from_spec(_sp)
    _sp.loader.exec_module(_mo)          # import only; the server starts under __main__
    return _mo


def _fx_state(**over):
    st = {
        "watch_asof": "2026-11-18 04:10:02 KL", "bridge": "up",
        "positions_now": [
            {"id": "6001", "action": "buy", "sym": "XAUUSD", "time": "2026-11-17 21:00:00", "vol": 0.05,
             "open": 2650.0, "last": 2660.0, "sl": 2645.0, "tp": 2670.0, "profit": 50.0,
             "r_now": 2.0, "age_min": 430},
            {"id": "6002", "action": "sell", "sym": "EURUSD", "time": "2026-11-17 22:00:00", "vol": 0.1,
             "open": 1.09, "last": 1.088, "sl": 1.09, "tp": 1.07, "profit": 20.0,
             "r_now": None, "age_min": 370}],
        "positions_total_pl": 70.0, "positions_open": 2,
        "orders": [{"sym": "XAUUSD", "skill": "S13-ichimoku-short", "risk": 100, "type": "sell stop"}],
        "book": {"n": 3, "items": [
            {"ticket": "771", "sym": "XAUUSD", "type": "buy stop", "state": "active", "price": 2655.5},
            {"ticket": "772", "sym": "EURUSD", "type": "sell limit", "state": "filled", "price": 1.0955},
            {"ticket": "773", "sym": "AMD", "type": "buy limit", "state": "active", "price": 151.2}]},
        "charts": {"XAUUSD": {"M15": {"bars": 60, "last": "2026-11-18T04:00:00", "patterns": 5,
                                      "enough": True},
                               "theme": "dollar", "fired_today": 2, "fired_rolling": 46,
                               "fired_days": ["2026-11-17", "2026-11-18"], "held": 2, "resting": 3,
                               "quote": {"bid": 2660.0, "ask": 2660.2}},
                   "AMD": {"M15": {"bars": 4, "last": None, "patterns": 0, "enough": False},
                            "theme": "equity", "fired_today": 0, "fired_rolling": 33, "fired_days": ["2026-11-18"],
          "held": 0, "resting": 1, "quote": {}, "thin": {"M15": 4}}},
        "charts_thin": {"AMD": {"M15": 4}},
        "playbook": {"cycle_s": 300, "risk_base": 100.0, "risk_band": [50.0, 200.0], "max_orders_day": 4,
                     "theme_cap": {"dollar": 600.0}, "timeframes": ["M15"], "bars_needed": {"M15": 15},
                     "orders": "pending only (limit/stop) — never market",
                     "red_window": "no new entries 20:15-22:30 KL (crypto exempt)",
                     "candle_library": "H1 + M15 closed bars",
                     "universe": {"XAUUSD": "dollar", "AMD": "equity"}}}
    st.update(over)
    return st


def _desk32(state):
    """A whole desk root holding nothing but these files, so what the card prints is what the files prove."""
    import shutil as _sh32
    d = tempfile.mkdtemp(prefix="fxwatch-")
    os.makedirs(os.path.join(d, "books"))
    json.dump(state, open(os.path.join(d, "state.json"), "w"))
    open(os.path.join(d, "desk_mode.json"), "w").write('{"entries_enabled": false}')
    open(os.path.join(d, "sentry_mac.py"), "w").write(
        '#!/usr/bin/env python3\n"""Trade Sentry — executor (demo account).\n"""\n')
    open(os.path.join(d, "sentry.out.log"), "w").write("x\n")
    open(os.path.join(d, "trades_log.jsonl"), "w").write("")
    open(os.path.join(d, "sentry_journal.md"), "w").write(
        "\n".join(["- **11-13 04:50 KL** **S13-ichimoku-short HIT — XAUUSD** · Risk $100 "
                    "· ticket ? sell stop 0.01@3875.9 sl3941.2 tp3837.1"] * 97
                   + ["- **11-18 04:10 KL** scan ok · book items 5"]) + "\n")
    return d


if _mp32 and _rp32:
    _mon32 = _load32("desk_monitor32", _mp32)
    _d32 = _desk32(_fx_state())
    _mon32.ROOT, _mon32.BOOKS = _d32, os.path.join(_d32, "books")
    _fx = _mon32.fx_section()
    _md = _mon32.to_markdown([], _fx, "t")
    _html = _mon32.to_html([], _fx, "t", "TRADING.md")
    check("the forex card now carries the terminal's own open trades, with R lived on each",
          _fx["n_positions"] == 2 and len(_fx["positions"]) == 2
          and _fx["positions"][0]["r_live"] == 2.0 and _fx["positions"][0]["pnl"] == 50.0
          and _fx["positions_total_pl"] == 70.0, str(_fx["positions"][:1]))
    check("...and the pending table is the resting orders off the book, not the day's send counter "
          "(filled/other states filtered out)",
          _fx["n_book"] == 3 and _fx["n_book_pending"] == 2 and _fx["n_pendings"] == 1
          and {p["sym"] for p in _fx["pendings"]} == {"XAUUSD", "AMD"},
          f"book={_fx['n_book']} pending={_fx['n_book_pending']} day={_fx['n_pendings']}")
    check("a chart row exists for every symbol x timeframe the build recorded, and it is a READING not a "
          "guess (bars, need, patterns, last bar)",
          len(_fx["chart_rows"]) == 2 and all(
              set(("sym", "tf", "bars", "need", "enough", "patterns", "last")) <= set(r)
              for r in _fx["chart_rows"]), str(_fx["chart_rows"][:1]))
    check("too-few-bars is a visible state of its own: 'not scanned', never a silent zero-signal row",
          "not scanned" in _md and "not scanned" in _html
          and [r for r in _fx["chart_rows"] if not r["enough"]][0]["bars"] == 4
          and _fx["charts_thin"] == {"AMD": {"M15": 4}} and _fx["chart_rows"][0]["need"] == 15, str([r for r in _fx["chart_rows"] if not r["enough"]]))
    check("the build's own rule set is echoed from its own fields (cycle, risk band, caps, windows)",
          _fx["playbook"]["cycle_s"] == 300 and _fx["playbook"]["max_orders_day"] == 4
          and "20:15-22:30" in _md and "pending only" in _md, str(_fx["playbook"].get("risk_band")))
    check("per-trade risk on the card comes from the build, not from a number remembered in the page",
          _fx["sizing"].get("source", "").startswith("published by the build")
          and _fx["sizing"]["base_risk"] == 100.0 and "per-trade **$100**" in _md, str(_fx["sizing"]))
    check("the two open-book measurements are shown side by side and labelled, because they are not the "
          "same quantity (5 journal items vs 3 in the state read vs 2 positions)",
          _fx["n_journal_items"] == 5 and "book items 5" in _md and _fx["n_positions"] == 2
          and "book items" in _md, str((_fx["n_journal_items"], _fx["n_book"], _fx["n_positions"])))
    # The build's send result never carries an order id (all 97 of its journalled HIT lines read `ticket ?`),
    # so no page can honestly attach a skill to a live position. Saying so is the feature.
    check("and it says out loud that a position cannot be tied to the skill that opened it",
          _fx["n_hits"] == 97 and _fx["n_no_ticket"] == 97 and "not knowable from these files" in _md
          and "not knowable" in _html, f"{_fx['n_no_ticket']}/{_fx['n_no_ticket']}")
    check("a position whose stop sits on its entry has NO R scale: the cell reads 'no stop distance', "
          "not 0R and not a division by zero",
          _fx["positions"][1]["r_live"] is None and "no stop distance" in _md and "no stop distance" in _html
          and "NoneR" not in _md and "NoneR" not in _html, str(_fx["positions"][1]))
    # Every one of these came from reading the REAL state.json off the Mac, not the fixture: a short printed
    # -0.415R while its PnL was +$50.96, "fired today" summed six days, ages vanished because the terminal
    # writes a "T" in its timestamps, and "14 of its daily limit of 4" implied a cap the build only treats as
    # advisory. The checks below are those four bugs, as rules.
    _fx_np = _mon32.fx_section()
    _md_np = _mon32.to_markdown([], _fx_np, "t")
    check("a symbol the build is HOLDING is marked as such in the matrix, so the 25 rows are not all equal",
          _fx_np["chart_rows"] and any(r.get("open_pos") for r in _fx_np["chart_rows"])
          and "●" in _md_np and "●" in _mon32.to_html([], _fx_np, "t", "TRADING.md"),
          str([r.get("open_pos") for r in _fx_np["chart_rows"]]))
    check("held-but-not-quoted is called out in words (a position on a feed the charts did not answer for)",
          "a symbol is held but was not quoted this cycle" in _mon32.to_markdown(
              [], dict(_fx_np, chart_rows=[{"sym": "EURUSD", "tf": "M15", "bars": 0, "need": 15,
                                            "enough": False, "patterns": 0, "last": None, "theme": "dollar",
                                            "fired_today": 0, "fired_rolling": 0, "bid": None, "ask": None,
                                            "open_pos": 1, "no_quote": True, "short": None}]), "t"))
    check("a cap the build only ADVISES is never printed as a limit: the card says advisory and quotes the note",
          "advisory, not enforced" in _mon32.to_markdown(
              [], dict(_fx_np, caps_advisory=True, n_advisory=6, advisory_last="entry #15 over soft cap"), "t")
          and "advisory" in _mon32.to_html([], dict(_fx_np, caps_advisory=True, n_advisory=6,
                                                   advisory_last="x"), "t", "TRADING.md"))
    check("the day-counter line is labelled for what it is (sends today), not 'pendings', next to the real "
          "book count",
          "sends today (its day counter)" in _md_np and _fx_np["pendings_word"].startswith("sends today"),
          str(_fx_np.get("pendings_word")))
    check("the matrix shows the per-day count AND the rolling one, so a six-day list cannot be read as a day",
          "decided today" in _md_np and "(rolling)" in _md_np
          and "decisions, not orders" in _md_np
          and [r for r in _fx_np["chart_rows"]][0].get("fired_rolling") is not None,
          str(_fx_np["chart_rows"][:1]))

    _d32b = _desk32({"orders": [{"sym": "XAUUSD", "skill": "S1-x", "risk": 100, "type": "buy stop"}],
                     "bridge": "up"})
    _mon32.ROOT = _d32b
    _fx_old = _mon32.fx_section()
    _md_old = _mon32.to_markdown([], _fx_old, "t")
    _html_old = _mon32.to_html([], _fx_old, "t", "TRADING.md")
    check("an OLD resident (no watch fields) degrades to 'not published by the build' on both pages, with "
          "no empty table dressed up as a zero",
          _fx_old["watch_published"] is False and _fx_old["n_positions"] is None
          and not _fx_old["chart_rows"] and "not published by the build" in _md_old
         
          and "not published by the build" in _html_old, str(_fx_old["watch_published"]))
    check("...and its open count falls back to the journal figure WITH the journal's own words, never "
          "presented as a position count",
          _fx_old["n_journal_items"] == 5 and "positions AND" in _md_old
          and "the terminal's own open positions" not in _md_old, str(_fx_old["positions_label"]))
    _t32_old = time.time() - 3600
    os.utime(os.path.join(_d32, "state.json"), (_t32_old, _t32_old))
    _mon32.ROOT = _d32                      # back to the FULL desk: staleness is about a live build going quiet
    _fx_stale = _mon32.fx_section()
    check("staleness is measured off the state file's own mtime and spelled out (a quiet job must not look "
          "healthy just because the page still renders)",
          _fx_stale["watch_stale"] is True and _fx_stale["book_age_min"] > 15
          and "STALE" in _mon32.to_markdown([], _fx_stale, "t"), str(_fx_stale["book_age_min"]))
    _d32e = _desk32(_fx_state(watch_error="KeyError: 'bars'"))
    _mon32.ROOT = _d32e
    _fxe = _mon32.fx_section()
    check("the build's own reporting failure is quoted verbatim instead of being swallowed (a monitor that "
          "hides its own breakage is the worst kind of lie)",
          _fxe["watch_error"] == "KeyError: 'bars'" and "KeyError" in _mon32.to_markdown([], _fxe, "t"),
          str(_fxe["watch_error"]))
    for _dd in (_d32, _d32b, _d32e):
        import shutil as _sh32
        _sh32.rmtree(_dd, ignore_errors=True)

    _rad32 = _load32("trade_radar32", _rp32)
    _blk = _rad32.fx_charts_block(_fx_state())
    check("the radar reads the SAME published fields, from the file the snapshot already opened — it adds no "
          "fetch of its own",
          _blk["published"] is True and len(_blk["rows"]) == 2 and _blk["thin"] == ["AMD/M15"]
          and _blk["positions_open"] == 2 and _blk["book_n"] == 3, str(_blk["thin"]))
    check("...and it carries the chart keys + bar minimums so the page cannot reorder them itself",
          _blk["tfs"] == ["M15"] and _blk["need"] == {"M15": 15}, str(_blk["tfs"]))
    _blk_old = _rad32.fx_charts_block({"orders": []})
    check("the radar's forex block also refuses to invent: no charts in the file means published=False",
          _blk_old["published"] is False and _blk_old["rows"] == [], str(_blk_old["published"]))
    _blk_bad = _rad32.fx_charts_block("not-a-dict")
    check("a half-written state.json (the classic accident) yields the empty block, never a traceback on "
          "the page", isinstance(_blk_bad, dict) and _blk_bad["published"] is False, str(type(_blk_bad)))
    _src32 = open(_rp32, encoding="utf-8").read()
    check("the radar page renders the matrix in its own table, with the header built from the build's "
          "timeframe list",
          'id="fx"' in _src32 and 'id="fxnote"' in _src32 and "tfs.map(t=>'<th>'+t+'</th>')" in _src32,
          "")
    check("and its column is labelled for what the number is (once-a-day KEYS = decisions, not orders)",
          "Decided today" in _src32 and "DECISIONS, not orders" in _src32
          and "<th>Fired today</th>" not in _src32,
          [l.strip()[:70] for l in _src32.splitlines() if "Fired" in l])
    check("the radar gains exactly one payload key for it, and that key is cut out of the state file the "
          "snapshot ALREADY read (a second fetch would be a second truth)",
          _src32.count('snap["fx_charts"]') == 1
          and 'snap["fx_charts"] = fx_charts_block(snap.get("sentry_state") or {})' in _src32,
          str(_src32.count('snap["fx_charts"]')))
    check("...and none of this opened a route or a page: the allow-list the earlier section pins is the "
          "same seven it was, and no lab/cctv coupling crept back in",
          '"/cctv.json"' in _src32 and '"/lab"' not in _src32 and '"/fxcharts"' not in _src32, "")
    _jsx = _re32.search(r"<script>(.*?)</script>", _rad32.HTML, _re32.S)
    if _shutil32.which("node") and _jsx:
        _jf = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False)
        _jf.write(_jsx.group(1)); _jf.close()
        check("the page's JavaScript — including the new matrix — parses as JavaScript",
              _sp32.run(["node", "--check", _jf.name], capture_output=True).returncode == 0)
        _os32.unlink(_jf.name)
    _msrc32 = open(_mp32, encoding="utf-8").read()
    check("neither page reached for the terminal to answer this: the desk still imports no socket, no "
          "subprocess, no HTTP client",
          not any(k in _msrc32 for k in ("urllib", "requests", "socket", "subprocess", "22346")),
          "monitor stays file-only")
else:
    check("monitor.py and trade_radar.py are both in this folder for section 32", False,
          str((_mp32, _rp32)))

# ---- the producer: only checkable where the MT5 build actually lives (it is not part of the GitHub release) ----
_sm32 = _asset("sentry_mac.py") or _asset("tools/mac/sentry_mac.py")
_src32 = open(_rp32, encoding="utf-8").read() if _rp32 else ""
if _sm32:
    _ssm32 = open(_sm32, encoding="utf-8").read()
    check("the resident publishes the watch itself (publish_watch), and does it AFTER the cycle's try, so a "
          "degraded cycle still reports what it last saw",
          "def publish_watch" in _ssm32 and "publish_watch(state, quotes, tf_map, positions, chart_thin, "
          "positions)" in _ssm32 and "state[\"watch_error\"]" in _ssm32, "")
    check("the scan gate and the page share ONE bar-minimum table (no second copy to drift)",
          "TF_MIN = {\"M5\": 25, \"M15\": 15, \"H1\": 60, \"H4\": 30, \"D1\": 8}" in _ssm32
          and "len(m5) < 25" not in _ssm32 and "len(b) < TF_MIN[t]" in _ssm32, "")
    check("the watch block cannot break the bot: it is wrapped in its own try, and save_state follows it "
          "unconditionally",
          _ssm32.count("save_state(state)") >= 1 and "except Exception as _we" in _ssm32
          and _ssm32.index("save_state(state)") > _ssm32.index("state[\"watch_error\"]"), "")
    check("the guardrails are untouched by any of this (the watch publishes them, it does not set them)",
          all(k in _ssm32 for k in ("MAX_SENTRY_ORDERS_DAY = 4", "pending order", "self_size")), "")
    _mo32 = _load32("sm32", _sm32)
    _raw32 = ('{"position_id": "9002", "action": "sell", "symbol": "EURUSD", '
              '"create_time": "2026-11-17T20:59:52", "volume": 1.04, "price_open": 1.10122, '
              '"price_last": 1.10073, "stop_loss": 1.1024, "take_profit": 1.09946, "profit": 50.96} '
              '{"position_id": "9003", "action": "buy", "symbol": "XAUUSD", '
              '"create_time": "2026-11-18 03:00:00", "volume": 0.05, "price_open": 2650.0, '
              '"price_last": 2645.0, "stop_loss": 2645.0, "take_profit": 2670.0, "profit": -25.0}')
    _st32 = {"day": "2026-11-18",
             "fired_today": ["FIRE|XAUUSD|C-M15-engulfing|2026-11-18", "FIRE|XAUUSD|S21|2026-11-17",
                             "FIRE|XAUUSD|S13|2026-11-13", "FIRE|EURUSD|S2-spring|2026-11-18"],
             "seen_candles": ["XAUUSD|M15|engulfing|t"], "orders": []}
    _tfm32 = {"XAUUSD": dict((t, [{"t": "2026-11-18T04:00:00"}] * _mo32.TF_MIN[t]) for t in _mo32.TFS)}
    _mo32.publish_watch(_st32, {"XAUUSD": {"bid": 2645.0, "ask": 2645.2}}, _tfm32, _raw32, {},
                        '{"order_id": "771", "symbol": "GBPUSD", "type": "buy stop", "state": "active", '
                        '"price_order": 1.32}')
    _pp32 = {x["id"]: x for x in _st32["positions_now"]}
    check("a SHORT moving in its favour is POSITIVE R (the stop distance is a distance, not a signed "
          "number — a card that printed -0.415R beside +$50.96 taught this one)",
          _pp32["9002"]["r_now"] == 0.415, str(_pp32["9002"]))
    check("a long sitting exactly on its stop reads -1.0R, and a stop ON the entry still gives None",
          _pp32["9003"]["r_now"] == -1.0, str(_pp32["9003"]))
    check("the terminal's ISO timestamp (with its T) is parsed, so age is not silently dropped",
          isinstance(_pp32["9002"]["age_min"], int) and _pp32["9002"]["age_min"] >= 0,
          str(_pp32["9002"]["age_min"]))
    check("`fired_today` is filtered on the day the build stamps, with the unfiltered count kept beside it",
          _st32["charts"]["XAUUSD"]["fired_today"] == 1
          and _st32["charts"]["XAUUSD"]["fired_rolling"] == 3
          and _st32["charts"]["XAUUSD"]["fired_days"] == ["2026-11-13", "2026-11-17", "2026-11-18"],
          str(_st32["charts"]["XAUUSD"]))
    check("a symbol you hold but did not get quotes for still gets a chart row (bars 0, not scanned) — the "
          "row a monitor exists to show",
          _st32["charts"]["EURUSD"]["M15"]["bars"] == 0
          and _st32["charts"]["EURUSD"]["M15"]["enough"] is False and "GBPUSD" in _st32["charts"],
          str(sorted(_st32["charts"])))
    check("and the radar surfaces that same per-day/rolling pair from the state file",
          '"fired": c.get("fired_today")' in _src32 and "fired_rolling" in _src32, "radar block")
else:
    check("sentry_mac.py is the Mac-side forex build and is not in this release — its producer checks run "
          "on the Mac (not a finding)", True, "skipped here by design")


# ---------- 33: a $50 book — sizing against the broker's floor, and grading off the terminal ----------
# The question that produced this section was "how much is left of my $50". Answering it exposed two things
# the build could not see: it never read its own account (so a $50 base was sized like the $101k demo it was
# actually running on), and it could not tell "too small to trade" from "no signal" (a size under 0.01 lot
# returned 0 and nothing was journalled). Both are fixed in the producer; the join is what makes the answer
# measurable — before it, 94 of 94 SENT trades had no result while the paper track of REJECTED candidates
# carried the win rate. These checks are mostly about the numbers a card is not allowed to invent.
print("\n== 33: small-account sizing + the order-id join")
_HERE33 = os.path.dirname(os.path.abspath(__file__))
_PROD33 = next((p for p in (os.path.join(_HERE33, "..", "sentry_mac.py"),
                            os.path.join(_HERE33, "tools", "mac", "sentry_mac.py"),
                            "/home/user/sentry_mac.py") if os.path.exists(p)), None)
if _PROD33 is None:
    check("the forex producer is not in this release (it is Mac-side, by design) — its own checks run on the "
          "Mac via tools/mac/fx_watch_test.py (skipped here)", True, "skipped: no sentry_mac.py next to the repo")
    _sm33 = None
else:
    _sm33 = _load32("fx_prod33", _PROD33)
    _sm33.use_fallback()          # the classic five, so the specs below are fixed and not broker-dependent


def _sr(sym, dist, risk, eq, frac=0.10):
    return _sm33.size_report(sym, dist, risk, eq, frac)


if _sm33:
    _big = _sr("EURUSD", 0.0045, 78.0, 101155.96)
    check("the guard is a NO-OP on the account that is actually running: $101k equity sizes EURUSD at the "
          "same 0.17 lot / $76.50 risk it did before this change, uncapped",
          _big["verdict"] == "ok" and abs(_big["lots"] - 0.17) < 1e-9 and abs(_big["risk"] - 76.5) < 0.01
          and _big["capped"] is False, str(_big))
    _small = _sr("EURUSD", 0.0045, 78.0, 50.0)
    check("on a $50 base the SAME signal cannot risk $78 (156% of it), so the ceiling cuts it to $5.00 and "
          "the size lands on the broker's 0.01 minimum",
          _small["verdict"] == "ok" and _small["capped"] is True and abs(_small["lots"] - 0.01) < 1e-9
          and abs(_small["risk"] - 4.5) < 0.01 and _small["risk_capped_from"] == 78.0, str(_small))
    _gold = _sr("XAUUSD", 33.40, 78.0, 50.0)
    check("...and XAUUSD on that same $50 base is REFUSED, not resized: the broker's 0.01 lot of gold already "
          "risks $33.40 = 66.8% of the account, which no ceiling of ours should permit",
          _gold["verdict"] == "min_lot_too_big" and _gold["lots"] == 0.0 and _gold["min_lot_risk"] == 33.4
          and "66.8%" in _gold["why"] and "cannot be traded on this base" in _gold["why"], str(_gold))
    check("an unread equity never becomes an unlimited licence: the clamp is skipped and the reason is stated",
          _sr("EURUSD", 0.0045, 78.0, None)["capped"] is False
          and "not checked" in _sr("EURUSD", 0.0045, 78.0, None)["why"], "")
    check("max_frac 0 (the desk can switch the guard off) clamps nothing and refuses nothing",
          _sr("EURUSD", 0.0045, 78.0, 50.0, 0.0)["capped"] is False
          and _sr("XAUUSD", 33.40, 78.0, 50.0, 0.0)["verdict"] == "ok", "")
    check("a zero stop distance is its own verdict, and sizes nothing (a stop ON the entry is not a free trade)",
          _sr("EURUSD", 0.0, 78.0, 50.0)["verdict"] == "no_stop"
          and _sr("EURUSD", 0.0, 78.0, 50.0)["lots"] == 0.0, "")
    check("a size above the broker's own maximum is refused rather than clamped down in silence",
          _sr("EURUSD", 0.0045, 1e9, None)["verdict"] == "over_max_lot", "")
    _nv = _sr("NVDA", 2.5, 78.0, 50.0)
    check("the floor is what the TERMINAL published per symbol (volume_min), not a guessed 0.01 — a share "
          "cannot be bought in hundredths, so the equity cap sizes 2 shares here and 0.01 lots there",
          _sm33.VSPEC["EURUSD"][0] == 0.01 and _sm33.VSPEC["NVDA"][0] == 1.0
          and _nv["verdict"] == "ok" and abs(_nv["lots"] - 2.0) < 1e-9 and _nv["min_lot_risk"] == 2.5, str(_nv))

    # ---- the send reply, read properly for the first time ----
    _ref = ('{"jsonrpc":"2.0","id":4,"result":{"isError":false,"content":[{"type":"text","text":"{\\n'
            '\\"retcode\\": 10015, \\"retcode_details\\": \\"Invalid price\\" \\n}\\"}]}}')
    _d = _sm33.parse_send_result(_ref)
    check("the refusal this build has been logging 121 times parses into its actual reason now "
          "(retcode 10015 / Invalid price), instead of a 200-char raw dump",
          _d["retcode"] == 10015 and _d["details"] == "Invalid price" and _d["ok"] is False, str(_d)[:200])
    _ok1 = _sm33.parse_send_result(r'text":"{\n\"retcode\": 10009, \"order\": \"59381656536\" }')
    _ok2 = _sm33.parse_send_result('{"retcode": 10009, "order_id": 59381656537, "deal": 59381656538}')
    check("an accepted send yields the order id whether the field is quoted, bare, called order or order_id — "
          "the alias hunt is the whole reason six days of fills went unattributed",
          _ok1["ok"] and _ok1["ticket"] == "59381656536" and _ok2["ticket"] == "59381656537"
          and _ok2["ticket_key"] in ("order_id", "order"), "%s / %s" % (_ok1, _ok2))
    check("accepted-but-unnamed is still accepted: ok True, ticket None (the trade is real, the key is missing)",
          _sm33.parse_send_result(r'"retcode": 10009, "retcode_details": "Request accepted"')["ok"] is True
          and _sm33.parse_send_result('"retcode": 10009')["ticket"] is None, "")
    check("an MCP-level error is a rejection, not a mystery retcode",
          _sm33.parse_send_result('{"result":{"isError\\":true,"content":[{"text":"not permitted"}]}}')["rejected"],
          "")

    # ---- the join: our sent rows to the terminal's closed positions ----
    _cmt = _sm33.comment_for("S21-pivot-S1-short")
    check("the comment is matched at the terminal's own 31-char limit, because that is what arrives on the wire",
          _cmt == ("Sentry S21-pivot-S1-short") and len(_sm33.comment_for("C" * 60)) == 31, _cmt)
    _rows = [
        {"rid": "A", "sym": "EURUSD", "skill": "S1-pullback-long", "fired": True, "risk": 50.0,
         "ts": "2026-11-18 04:34"},
        {"rid": "B", "sym": "EURUSD", "skill": "S1-pullback-long", "fired": True, "risk": 50.0,
         "ts": "2026-11-16 12:00"},
        {"rid": "C", "sym": "XAUUSD", "skill": "S13-ichimoku-short", "fired": True, "risk": 100.0,
         "ts": "2026-11-18 02:00", "ticket": "9002"},
        {"rid": "D", "sym": "AMD", "skill": "S16-inside-long", "fired": True, "risk": 60.0,
         "ts": "2026-11-18 05:00"},
        {"rid": "E", "sym": "AMD", "skill": "S16-inside-long", "fired": False, "result": "win", "R": 1.0}]
    _cls = [{"ticket": "9001", "sym": "EURUSD", "comment": _sm33.comment_for("S1-pullback-long"),
             "profit": 74.0, "open_time": "2026-11-17T20:40:00", "close_time": "2026-11-17T22:00:00"},
            {"ticket": "9002", "sym": "XAUUSD", "comment": "someone else's order", "profit": -100.0,
             "open_time": "2026-11-17T18:10:00", "close_time": "2026-11-17T19:00:00"},
            {"ticket": "9003", "sym": "AMD", "comment": _sm33.comment_for("S16-inside-long"),
             "profit": 12.0, "open_time": "2026-11-17T21:05:00", "close_time": "2026-11-17T22:13:11"},
            {"ticket": "9004", "sym": "EURUSD", "comment": _sm33.comment_for("S1-pullback-long"),
             "profit": -50.0, "open_time": "2026-11-16T04:00:00", "close_time": "2026-11-16T06:00:00"}]
    _upd = _sm33.match_closes(_rows, _cls)
    _by = {u["rid"]: u for u in _upd}
    check("a sent row is graded from the close whose ORDER COMMENT names the skill that sent it "
          "(+74.00 on a $50 stop = +1.48R, not a rounded ±1)",
          "A" in _by and _by["A"]["result"] == "win" and _by["A"]["R"] == 1.48
          and _by["A"]["via"] == "comment", str(sorted(_by)))
    check("two closes for the same skill+symbol cannot both land on one row, and the row already graded by "
          "ticket is graded by TICKET even when its comment belongs to someone else",
          "B" in _by and _by["B"]["ticket"] == "9004" and _by["B"]["result"] == "loss"
          and _by["C"]["ticket"] == "9002", str(sorted(_by)))
    check("the COMMENT window is 6 hours: a close that opened 47 days before the row was sent is not a "
          "result for it (this exact hole is what the first version of this join fell into)",
          _by["D"]["ticket"] == "9003" and _by["D"]["via"] == "comment"
          and _sm33.match_closes([dict(_rows[3], ts="2026-11-18 05:00")],
                                 [dict(_cls[2], open_time="2026-10-01T21:05:00")]) == [], str(sorted(_by)))
    check("a TICKET gets 10 days instead of 6 hours (a limit order rests before it fills, and tl_log's ts is "
          "stamped at send), but even a ticket is not trusted past that; a comment-only row with an "
          "unreadable ts matches nothing at all",
          len(_sm33.match_closes([dict(_rows[3], ticket="9003", ts="2026-11-14 21:00")], [_cls[2]])) == 1
          and _sm33.match_closes([dict(_rows[3], ts="whenever")], [_cls[2]]) == []
          and _sm33.match_closes([dict(_rows[3], ticket="9003")],
                                 [dict(_cls[2], open_time="2026-10-01T21:05:00")]) == [], "")
    check("the paper track is never re-graded by the join: a row that already has a result is skipped",
          "E" not in _by, str(sorted(_by)))
    check("a sent trade with no close yet stays ungraded — an open position is not a result and the row must "
          "say nothing rather than guess",
          _sm33.match_closes([{"rid": "F", "sym": "GBPUSD", "skill": "S2-breakout-long", "fired": True,
                               "risk": 80.0, "ts": "2026-11-18 04:00"}], _cls) == [], "")
    check("the profit figure carries the currency it is denominated in, so a demo USD can never be read as "
          "a wallet balance and a non-USD account cannot be silently printed as dollars",
          _sm33.live_record([], "EUR")["currency"] == "EUR" and _sm33.live_record([])["currency"] == "USD", "")
    _lr = _sm33.live_record([dict(r, **_by.get(r["rid"], {})) for r in _rows]
                            + [{"rid": "G", "sym": "GBPUSD", "skill": "S2", "fired": True, "risk": 80.0}])
    check("live_record counts sent / graded / ungraded separately, and takes net R only over graded rows "
          "(+1.48 -1.0 -1.0 +0.2 = -0.32, with E excluded because it was never sent)",
          _lr["sent"] == 5 and _lr["graded"] == 4 and _lr["ungraded"] == 1
          and abs(_lr["net_r"] + 0.32) < 0.01 and _lr["wins"] == 2 and _lr["losses"] == 2
          and _lr["win_rate"] == 50.0, str(_lr))
    check("...and win_rate is None (not 0%) when there is nothing to divide by",
          _sm33.live_record([])["win_rate"] is None and _sm33.live_record([])["sent"] == 0, "")

    # ---- grading writes through to the log, and only once ----
    _d33 = tempfile.mkdtemp(prefix="tl33-")
    _tl33 = os.path.join(_d33, "trades_log.jsonl")
    open(_tl33, "w").write(json.dumps(_rows[0]) + "\n" + json.dumps(_rows[3]) + "\n")
    _old_tl, _old_state = _sm33.TL_PATH, _sm33.STATE_F
    _sm33.TL_PATH = _tl33
    try:
        check("tl_grade_terminal writes result, real R, the profit, the ticket and WHERE it came from",
              _sm33.tl_grade_terminal({"rid": "A", "ticket": "9001", "profit": 74.0, "R": 1.48,
                                       "result": "win"}) is True
              and json.loads(open(_tl33).read().split("\n")[0])["grade_source"] == "terminal",
              open(_tl33).read().strip())
        _before = open(_tl33).read()
        check("...and will not overwrite a row that already has a result (a re-run cannot double-count)",
              _sm33.tl_grade_terminal({"rid": "A", "ticket": "9001", "profit": -999.0, "R": -9.9,
                                       "result": "loss"}) is True
              and json.loads(open(_tl33).read().split("\n")[0])["R"] == 1.48
              and json.loads(open(_tl33).read().split("\n")[0])["result"] == "win", _before[:80])
        check("has_ungraded_sent is the only thing that decides whether to pay for the close history: True "
              "while row D still waits, False when every sent row has an outcome",
              _sm33.has_ungraded_sent(_sm33.tl_rows()) is True
              and _sm33.has_ungraded_sent([{"fired": True, "result": "win"}, {"fired": False}]) is False
              and _sm33.has_ungraded_sent([]) is False, str(_sm33.tl_rows())[:90])
    finally:
        _sm33.TL_PATH, _sm33.STATE_F = _old_tl, _old_state

    # ---- the fetch, and the sentences both pages print ----
    check("the close history is fetched only when something is outstanding; the account is fetched always "
          "(the guard is meaningless without it)",
          "@@HISTORY" in _sm33.build_fetch(need_hist=True) and "@@HISTORY" not in _sm33.build_fetch(False)
          and "@@ACCOUNT" in _sm33.build_fetch(False), "")
    check("the account line says what kind of money it is — a demo base may not read like a wallet figure",
          "DEMO account" in _sm33.fmt_account_line({"login": "5058788329", "server": "MetaQuotes-Demo",
                                                     "type": "demo", "equity": 101155.96})
          and "real money" in _sm33.fmt_account_line({"type": "real", "equity": 50.0}), "")
    check("...an unrecognised type is reported as unrecognised, and a missing type claims neither",
          "will not guess" in _sm33.fmt_account_line({"type": "centum"})
          and "reported no account type" in _sm33.fmt_account_line({"login": "1"}), "")
    _gl = _sm33.fmt_guard_line({"equity": 50.0, "max_frac": 0.10, "risk_cap": 5.0, "capped_today": 2,
                                "min_lot": {"EURUSD": 0.01}, "refused_today": {"min_lot_too_big": 3}})
    check("the sizing line answers the question the desk gets asked: what one trade may risk, on WHICH floor, "
          "and what that floor refused today",
          "10% of equity ($5.00 of $50.00)" in _gl and "EURUSD 0.01 lot" in _gl
          and "min_lot_too_big x3" in _gl and "2 trade(s) today had their risk cut" in _gl, _gl)
    check("no equity read says 'NOT applied' out loud — silence here would read as 'nothing to worry about'",
          "NOT applied" in _sm33.fmt_guard_line({"equity": None, "max_frac": 0.10}), "")
    check("a live record with no grades says a sent order is not a result, and does not print a win rate",
          "not a result" in _sm33.fmt_live_line({"sent": 94, "graded": 0}),
          _sm33.fmt_live_line({"sent": 94, "graded": 0}))
    check("...with grades it quotes net R and the dollars, all of them read from the terminal",
          "+8.56R" in _sm33.fmt_live_line({"sent": 79, "graded": 76, "wins": 47, "losses": 29,
                                           "net_r": 8.56, "net_usd": 1229.83, "win_rate": 61.8,
                                           "from_terminal": 76, "ungraded": 3}),
          _sm33.fmt_live_line({"sent": 79, "graded": 76, "wins": 47, "losses": 29, "net_r": 8.56,
                               "net_usd": 1229.83, "win_rate": 61.8, "from_terminal": 76, "ungraded": 3}))

# ---- the pages: pass it through, and print a gap when the build is older ----
if _mp32 and _rp32:
    _m33 = _load32("desk_monitor33", _mp32)
    _st33 = _fx_state(account={"login": "5058788329", "server": "MetaQuotes-Demo", "type": "demo",
                               "equity": 50.0, "balance": 50.0, "currency": "USD", "margin_mode": "hedging",
                               "asof": "2026-11-18 05:30:00 KL"},
                      live_record={"sent": 3, "graded": 2, "wins": 2, "losses": 0, "ungraded": 1,
                                   "net_r": 1.9, "net_usd": 9.4, "win_rate": 100.0, "from_terminal": 2},
                      sizing={"equity": 50.0, "max_frac": 0.1, "risk_cap": 5.0, "capped_today": 1,
                              "min_lot": {"EURUSD": 0.01}, "refused_today": {"min_lot_too_big": 4}},
                      account_line="login 5058788329 · account demo — a DEMO account: the orders really do go "
                                   "to the terminal, the money does not come from you",
                      guard_line="one minimum-size position may not risk over 10% of equity ($5.00 of $50.00)",
                      live_line="of the 3 trades SENT, 2 graded from the terminal's own closes: 2W/0L")
    _d33b = _desk32(_st33)
    _m33.ROOT, _m33.BOOKS = _d33b, os.path.join(_d33b, "books")
    _c33 = _m33.fx_section()
    _md33 = _m33.to_markdown([], _c33, "t")
    _htm33 = _m33.to_html([], _c33, "t", "TRADING.md")
    check("the card shows WHICH account and what kind of money it is, in both renderers",
          "5058788329" in _md33 and "DEMO account" in _md33 and "5058788329" in _htm33
          and _c33["account"]["equity"] == 50.0, "")
    check("...the sizing floor and the live record are on the card too, and they are the build's own strings "
          "(the monitor adds no arithmetic of its own)",
          "minimum-size position may not risk over 10%" in _md33 and "2W/0L" in _md33
          and "sizing floor" in _htm33 and "live record" in _htm33, "")
    _d33c = _desk32(_fx_state())          # a resident from before this change
    _m33.ROOT = _d33c
    _c33b = _m33.fx_section()
    _md33b = _m33.to_markdown([], _c33b, "t")
    check("an older resident that publishes no account gets 'account type not published', never a guessed one",
          _c33b["account_line"] == "" and "account type not published" in _md33b, "")
    check("...and none of the three lines is rendered at all — an absent figure prints as nothing, not as $0 "
          "or 0 trades, and no equity line replaces the account line",
          not any(l.strip().startswith(("- equity ", "- sizing floor:", "- live record · ", "- login "))
                  for l in _md33b.splitlines())
          and _c33b["guard_line"] == "" and _c33b["live_line"] == ""
          and _c33b["account"] == {} and _c33b["live_record"] == {} and _c33b["equity"] is None,
          "\n".join(l[:70] for l in _md33b.splitlines()
                     if l.strip().startswith(("- equity ", "- sizing", "- live", "- login")))[:200])
    check("the playbook band the OLD build did publish is still shown, labelled as published and not quietly "
          "relabelled as the guard (the guard is the new, separate set of figures)",
          _c33b["sizing"].get("base_risk") == 100.0 and _c33b["sizing"].get("band") == [50.0, 200.0]
          and _c33b["sizing"].get("source") == "published by the build this cycle", str(_c33b["sizing"]))
    check("the money the terminal reported still reads as a distance in the table, not as the account: the "
          "card's own $ figures are TP/SL distances unless the line says equity",
          any(l.strip().startswith("| XAUUSD") for l in _md33b.splitlines()), "")
    # the pill's claim about WHICH KIND of money, and where the card learned it
    _m33.ROOT, _m33.BOOKS = _d33b, os.path.join(_d33b, "books")
    _c_kind = _m33.fx_section()
    check("with an account published, the pill's kind is the TERMINAL's answer, and the card says so",
          _c_kind["account_kind"] == "demo" and "reported by the terminal" in _c_kind["account_kind_src"],
          str(_c_kind["account_kind_src"]))
    check("...and that sentence is on the page in both renderers, so the claim carries its own source",
          "reported by the terminal" in _m33.to_markdown([], _c_kind, "t")
          and "reported by the terminal" in _m33.to_html([], _c_kind, "t", "TRADING.md"), "")
    _m33.ROOT, _m33.BOOKS = _d33c, os.path.join(_d33c, "books")
    open(os.path.join(_d33c, "sentry_mac.py"), "w").write(
        '#!/usr/bin/env python3\n"""Trade Sentry — executor (demo account).\n"""\n')
    _c_head = _m33.fx_section()
    check("an OLD build that publishes no account still falls back to the header comment, but the card labels "
          "that as an inference and not as a reading (this is the claim that was quietly overstated)",
          _c_head["account_kind"] == "demo" and "NOT from the terminal" in _c_head["account_kind_src"]
          and "NOT from the terminal" in _m33.to_markdown([], _c_head, "t"), str(_c_head["account_kind_src"]))
    _d33d = _desk32(_fx_state(account={"login": "77", "type": "text", "equity": 50.0}, account_line="x"))
    _m33.ROOT, _m33.BOOKS = _d33d, os.path.join(_d33d, "books")
    _c_odd = _m33.fx_section()
    check("a kind the card cannot map is NOT rounded to demo or real: the pill goes to 'account kind unknown' "
          "and the page quotes what the terminal actually said (this is exactly the reply that first arrived)",
          _c_odd["account_kind"] == "unknown" and "text" in _c_odd["account_kind_src"]
          and "account kind unknown" in _m33.to_markdown([], _c_odd, "t"), str(_c_odd["account_kind_src"]))
    _r33 = _load32("desk_radar33", _rp32)
    _fxr = _r33.fx_charts_block(_st33)
    # --- the account record, off the payload SHAPE the Mac actually sends (v4.7.9's first live cycle) ---
    # The inner JSON arrives escaped inside an MCP text part, and FETCH pipes it through `tr -d "\\"`. That
    # leaves the ENVELOPE's own {"type":"text"} in the same string as the account's "type":"demo" — and the
    # first version read the envelope, so the desk printed `account text`. Pinned here against the real reply.
    _acct_raw = (r'{"jsonrpc":"2.0","id":6,"result":{"isError":false,"content":[{"type":"text","text":"{n'
                 r'\"account\": {n\"server\": \"MetaQuotes-Demo\", \"broker\": \"MetaQuotes Ltd.\", '
                 r'\"login\": \"5058788329\", \"name\": \"Arena Trader\", \"type\": \"demo\", '
                 r'\"read_only\": false, \"margin_mode\": \"hedging\", \"balance\": 101155.96, '
                 r'\"equity\": 101155.96, \"currency\": \"USD\" },n\"terminal\": {n\"timestamp\":'
                 r'\"2026-11-17T21:49:52Z\"}}"}]}}')
    _ar = _acct_raw.replace("\\", "")            # what `tr -d "\\"` leaves on the wire
    _pa = _sm33.parse_account(_ar)
    check("the account type read from a live reply is the ACCOUNT's, not the MCP envelope's — the object is "
          "scoped before any field is read, so 'text' can never answer for 'demo'",
          _pa.get("type") == "demo" and _pa.get("login") == "5058788329"
          and _pa.get("equity") == 101155.96 and _pa.get("currency") == "USD"
          and _pa.get("read_only") is None, json.dumps(_pa))
    check("...and the desk sentence that comes out of it says what kind of money this is",
          "a DEMO account" in _sm33.fmt_account_line(_pa) and "101,155.96" in _sm33.fmt_account_line(_pa),
          _sm33.fmt_account_line(_pa))
    check("a reply naming no account object still parses its scalars, and an empty one yields {} (no "
          "half-built record claiming a balance)",
          _sm33.parse_account('{"type": demo, "equity": 50.0}')["type"] == "demo"
          and _sm33.parse_account("") == {} and _sm33.parse_account(None) == {}, "")

    check("the radar gets the same three sentences from the same state file (one truth, two pages)",
          _fxr["account_line"] == _st33["account_line"] and _fxr["guard_line"] == _st33["guard_line"]
          and _fxr["live_line"] == _st33["live_line"] and _fxr["live"]["graded"] == 2, "")
    check("...and it still adds no route: the radar's forex payload grows by keys inside fx_charts only",
          _rp32 and open(_rp32, encoding="utf-8").read().count('snap["fx_charts"]') == 1, "")

# ---------- 33b: the MARGIN floor — what an account can POST, not just what it can LOSE ----------
# Found by asking the broker's own calculator (trade_order_calc_margin) instead of assuming leverage: one
# share of NVDA costs $185.00 of margin and $185.00 notional, while its stop risks $2.50. A guard that only
# looks at risk says "ok, 2 shares" for a $50 account and the broker then refuses it — the exact silent
# disappearance this release was meant to end. Margin does not scale with balance, so it is a second,
# independent floor, and it is measured from the terminal because account_info publishes no leverage at all.
print("\n== 33b: the margin floor (posted vs lost)")
_PROD_SRC = open(_PROD33, encoding="utf-8").read() if _PROD33 else ""
if _sm33:
    check("the broker's answer is read from the reply AS IT ARRIVES: no symbol echo (there is none), ok must "
          "be true, and a figure in another currency is refused rather than compared against USD",
          _sm33.parse_margin('{"result":{"isError":false,"content":[{"text":"{ "ok": true, "margin": 10.9800,'
                             ' "currency": "USD" }"}]}}', "EURUSD", "USD") == 10.98
          and _sm33.parse_margin('"ok": true, "margin": 10.98, "currency": "JPY"', "EURUSD", "USD") is None
          and _sm33.parse_margin('"ok": false, "margin": 10.98', "EURUSD") is None
          and _sm33.parse_margin("", "EURUSD") is None, "")
    check("a parse helper that can never pass is WORSE than none: the first version demanded the symbol appear "
          "in a reply that does not echo it, which would have read as 'the broker refused' forever",
          "margin" not in _sm33.parse_margin.__doc__.lower()[:0] and _sm33.parse_margin(
              '{"ok": true, "margin": 26.6, "currency": "USD"}', "XAUUSD") == 26.6, "")

    # measured from the live terminal on 2026-11-18 via trade_order_calc_margin (margin follows PRICE, not
    # the account, so AMD is $510 here and not the $220 a hand-picked price suggested -- which is exactly
    # why the resident measures it instead of computing it from an assumed leverage)
    _M50 = {"EURUSD": 11.00, "GBPUSD": 13.21, "XAUUSD": 38.47, "NVDA": 158.71, "AMD": 510.63}
    _eq50 = 50.0
    _n_ok = _sm33.size_report("EURUSD", 0.0045, 78.0, _eq50, 0.10, margin=_M50["EURUSD"])
    check("EURUSD on $50 clears BOTH floors: $10.98 of margin against $50 of equity, and the 0.01 lot risks "
          "$4.50 once the risk cap bites -- so it trades at the minimum lot",
          _n_ok["verdict"] == "ok" and abs(_n_ok["lots"] - 0.01) < 1e-9 and _n_ok["margin"] == 11.00, str(_n_ok))
    _n_nv = _sm33.size_report("NVDA", 2.5, 78.0, _eq50, 0.10, margin=_M50["NVDA"])
    check("NVDA is refused on MARGIN, not on risk: the risk figure is the smallest on the board ($2.50/stop) "
          "and one whole share still costs $185 to post. The verdict is its own kind, so the desk can say "
          "'cannot be opened' rather than 'too risky'",
          _n_nv["verdict"] == "min_margin_too_big" and _n_nv["lots"] == 0.0 and _n_nv["margin_needed"] == 158.71
          and "cannot be opened at any risk size" in _n_nv["why"], str(_n_nv))
    check("...and the refusal names the unit it measured, so a reader sees this is about ONE SHARE, not a lot",
          "$158.71 of margin" in _n_nv["why"] and "1.0" in _n_nv["why"], _n_nv["why"][:160])
    check("gold is refused by the RISK floor (26.60 of margin fits, $33.40 of risk does not), which is how "
          "we know the two checks are separate and neither one is standing in for the other",
          _sm33.size_report("XAUUSD", 33.40, 78.0, _eq50, 0.10, margin=_M50["XAUUSD"])["verdict"]
          == "min_lot_too_big", "")
    check("the margin floor is a NO-OP on the account that is running: $185 of margin against $101k is not a "
          "constraint, and the sizes do not move by a cent",
          _sm33.size_report("NVDA", 2.5, 78.0, 101155.96, 0.10, margin=510.63)["verdict"] == "ok"
          and abs(_sm33.size_report("EURUSD", 0.0045, 78.0, 101155.96, 0.10,
                                    margin=10.98)["lots"] - 0.17) < 1e-9, "")
    check("an UNMEASURED margin never blocks and never claims clearance: the risk floor alone decides, and "
          "the report says the other check did not run",
          _sm33.size_report("NVDA", 2.5, 78.0, _eq50, 0.10)["verdict"] == "ok"
          and _sm33.size_report("NVDA", 2.5, 78.0, _eq50, 0.10)["margin"] is None, "")
    check("free margin, not equity, is what the check is honest about - the why says the account would have "
          "less once other positions are counted, so the number is never read as headroom",
          "not free margin" in _n_nv["why"], _n_nv["why"][-120:])

    _gl2 = _sm33.fmt_guard_line({"equity": 50.0, "max_frac": 0.10, "risk_cap": 5.0,
                                 "min_lot": {"EURUSD": 0.01, "NVDA": 1.0},
                                 "margin_floor": {"EURUSD": 10.98, "NVDA": 185.0}})
    check("the desk line prints both floors, so 'why is there no NVDA trade' is answerable from the page",
          "broker floor: EURUSD 0.01 lot, NVDA 1.0 lot" in _gl2
          and "margin for one unit: EURUSD $10.98, NVDA $185.00" in _gl2, _gl2)
    check("...and when the margin was never measured it says so on the same line, rather than letting the "
          "risk ceiling look like the whole story",
          "margin floor NOT measured" in _sm33.fmt_guard_line({"equity": 50.0, "max_frac": 0.10,
                                                                "min_lot": {"EURUSD": 0.01}}), "")
    check("no equity read prints no margin complaint either (there is nothing to compare against)",
          "NOT measured" not in _sm33.fmt_guard_line({"equity": None, "max_frac": 0.10,
                                                      "min_lot": {"EURUSD": 0.01}}), "")

    # the cache round-trips through the published state, which is how a restart keeps the check
    check("the floors the cycle used are published (min_lot AND margin_floor), so a restart re-measures "
          "nothing it already knows and the desk shows what was actually applied",
          '"margin_floor": {s: MARGIN[s] for s in (SYMS or []) if s in MARGIN}' in _PROD_SRC
          and 'MARGIN.update({str(k): float(v) for k, v in (state.get("margin_floor") or {}).items()'
          in _PROD_SRC, "")
    check("the measurement is capped and cached: at most 10 new symbols per cycle, only symbols not already "
          "known, through the same bridge as everything else (no new network path)",
          "for _s in _todo[:10]" in _PROD_SRC and "_todo = [s for s in SYMS if s not in MARGIN]" in _PROD_SRC
          and "trade_order_calc_margin" in _PROD_SRC, "")
    check("a symbol the terminal would not answer for is journalled as unchecked, so silence is not read as "
          "clearance",
          "margin floor NOT measured for" in _PROD_SRC
          and "same as being clear to trade" in _PROD_SRC, "")

    # and the pages must show the new verdict kind without knowing it exists
    if _mp32:
        _m33b = _load32("desk_monitor33b", _mp32)
        _d33e = _desk32(_fx_state(
            sizing={"equity": 50.0, "max_frac": 0.1, "risk_cap": 5.0, "capped_today": 0,
                    "min_lot": {"EURUSD": 0.01, "NVDA": 1.0}, "margin_floor": {"EURUSD": 10.98, "NVDA": 185.0},
                    "refused_today": {"min_margin_too_big": 6, "min_lot_too_big": 11}},
            guard_line=_sm33.fmt_guard_line({"equity": 50.0, "max_frac": 0.1, "risk_cap": 5.0,
                                             "min_lot": {"EURUSD": 0.01, "NVDA": 1.0},
                                             "margin_floor": {"EURUSD": 10.98, "NVDA": 185.0},
                                             "refused_today": {"min_margin_too_big": 6, "min_lot_too_big": 11}})))
        _m33b.ROOT, _m33b.BOOKS = _d33e, os.path.join(_d33e, "books")
        _c33e = _m33b.fx_section()
        _md33e = _m33b.to_markdown([], _c33e, "t")
        check("the desk renders the new verdict counts verbatim (it is a passthrough, so a verdict this page "
              "has never heard of still shows up)",
              "min_margin_too_big x6" in _md33e and "$185.00" in _md33e and "min_lot_too_big x11" in _md33e,
              [l[:100] for l in _md33e.splitlines() if "sizing floor" in l])
        check("...and the radar gets the same string, unedited",
              _load32("desk_radar33b", _rp32).fx_charts_block(_fx_state(guard_line=_c33e["guard_line"]))
              ["guard_line"] == _c33e["guard_line"], "")

# -*- coding: utf-8 -*-
"""A check that would have caught my own bug. The margin patch REPLACED the `chart_thin = {}` line instead of
inserting above it; the cycle is wrapped in a try/except, so the resident kept trading and journalling while
the forex watch died quietly for 17 hours (only `watch_error` showed it). These checks assert on LINE ORDER,
which is what actually broke, and on the fact that a swallowed error stays published."""
print("\n== 34: a deleted initialisation is a crash, not a warning (splice guard)")
if _PROD33:
    _src34 = open(_PROD33, encoding="utf-8").read()
    _L34 = _src34.split("\n")

    def _ln34(sub, frm=0):
        for k in range(frm, len(_L34)):
            if sub in _L34[k]:
                return k
        return -1

    _def = _ln34("chart_thin = {}")
    # searched FROM the definition onward: the earlier "first hit anywhere" landed inside publish_watch's own
    # body (line 281), which is before main() and made the ordering claim meaningless -- a bad test, not a
    # second bug.
    _use = _ln34("chart_thin[sym]", _def + 1)
    _call = _ln34("publish_watch(state,", _def + 1)
    check("chart_thin is INITIALISED in the cycle, before the loop that fills it and before the publish call "
          "(my splice deleted this exact line and the resident survived it, which is the worst kind of bug: "
          "the page keeps rendering, only forever 17 hours stale)",
          _def >= 0 and _use >= 0 and _call >= 0 and _def < _use < _call,
          "def=%d use=%d call=%d" % (_def + 1, _use + 1, _call + 1))
    check("...and the guard is symmetric: the name the failure was reported for is the one that was missing",
          'NameError' in ("chart_thin" if _def < 0 else "") or _def >= 0, "")
    check("a swallowed watch failure stays VISIBLE: publish_watch's exception is recorded into watch_error and "
          "the payload carries it, so 'the desk looks fine' is never the only evidence",
          'state["watch_error"]' in _src34 and '"error": st.get("watch_error")' in open(
              os.path.join(_HERE33, "tools", "mac", "trade_radar.py"), encoding="utf-8").read(), "")
    check("the cycle wraps the watch in its own try (kept deliberately: a dead watch must not stop the bot) "
          "-- so a static order check like the one above is the only thing that catches this class at all",
          _src34.count("watch_error") >= 2, "watch_error refs=%d" % _src34.count("watch_error"))
else:
    check("the resident is not next to the repo, so the splice guard runs on the Mac (skipped here)", True,
          "skipped: no sentry_mac.py")


# 35 — a price with too many decimals is a REFUSAL, not a rounding preference (retcode 10015).
# Found while answering "sentry down?": the watch had been dead 17 hours (see 34) and, next to it,
# 90 journal lines said "CHECK/SEND FAILED ... retcode 10015 Invalid price" (plus 124 verbatim
# copies of the same reply), 79 of the 90 on XAUUSD against 26 gold fills ever. Nothing in the build was wrong with size or signal: fire() hands the
# entry/sl/tp straight through from arithmetic, so the payload carried values like
# 1.3165645839210065 for a five-digit symbol, and MT5 answers that with "Invalid price" on the
# trade_check_pending_order call, before an order number exists. The journal printed the same order
# through rnd(), which is why every one of them looked fine on paper. The fix is one formatter,
# fmt_px, applied at the single place the payload is built and at the two trail sites, which had
# hardcoded five digits and so were wrong for gold and for the equity symbols.
print("\n== 35: what the terminal is actually sent (10015 / digits)")
if _PROD33 is None:
    check("the producer is not next to the repo, so the price-shape checks run on the Mac (skipped here)",
          True, "skipped: no sentry_mac.py")
else:
    import re as _re35
    import json as _json35

    def _dec35(s):
        return len(s.split(".")[1]) if "." in s else 0

    # the formatter itself, on the exact values the journal shows failing
    check("fmt_px clips a live offender to the symbols digits",
          _sm33.fmt_px("GBPUSD", 1.3165645839210065) == "%.*f" % (_sm33.DIGITS["GBPUSD"], 1.3165645839210065),
          repr(_sm33.fmt_px("GBPUSD", 1.3165645839210065)))
    _bad35 = []
    for _s35 in _sm33.SYMS[:]:
        _d35 = _sm33.DIGITS[_s35]
        for _k35 in range(7):
            _v35 = 1.3165645839210065 * (1 + _k35) if _s35 in ("EURUSD", "GBPUSD") else \
                   (2613.4150000000001 + _k35) if _s35 == "XAUUSD" else (154.13837845882833 + _k35)
            _o35 = _sm33.fmt_px(_s35, _v35)
            if _dec35(_o35) > _d35:
                _bad35.append("%s -> %s (digits %d)" % (_s35, _o35, _d35))
            if float(_o35) > _v35 and _o35 != repr(_v35):
                pass                      # either direction is legal; only precision is asserted
    check("no symbol in the classic five can produce a price with more decimals than it has digits",
          not _bad35, "; ".join(_bad35[:4]))
    check("a value fmt_px cannot read stays unread (a missing TP never becomes 0.00)",
          _sm33.fmt_px("EURUSD", None) is None, repr(_sm33.fmt_px("EURUSD", None)))
    check("a symbol the catalog has not described yet gets the documented five-digit default, not a pass-through",
          _sm33.fmt_px("NOSUCH", 1.23456789) == "1.23457", repr(_sm33.fmt_px("NOSUCH", 1.23456789)))

    # the shipped path, not a re-implementation: call send_order with the terminal stubbed out and
    # read back the curl payload it built.
    import tempfile as _tf35
    _tmp35 = _tf35.mkdtemp(prefix="s35desk")
    _old_state35, _old_mac35, _old_j35 = _sm33.STATE_F, _sm33.mac, _sm33.JOURNAL_F
    with open(os.path.join(_tmp35, "desk_mode.json"), "w") as _f35:
        _json35.dump({"entries_enabled": True}, _f35)
    _cap35 = {}

    def _stub35(cmd, timeout=120):
        _cap35["cmd"] = cmd
        return _json35.dumps({"result": {"isError": False,
                                         "content": [{"text": _json35.dumps({"retcode": 10009,
                                                                             "order": 59401583433})}]}})

    try:
        _sm33.STATE_F = os.path.join(_tmp35, "state.json")
        _sm33.mac = _stub35
        _sm33.JOURNAL_F = os.path.join(_tmp35, "sentry_journal.md")
        _st35 = {"orders": [], "logs": [], "theme_risk": {}, "day": "11-18"}
        _sm33.send_order(_st35, "GBPUSD", "sell stop", 0.28,
                         1.3165645839210065, 1.3195700000000001, 1.3109599999999995, "S21-pivot")
        _c35 = _cap35.get("cmd", "")
        _prices35 = _re35.findall(r"price\\*\"\s*:\s*([0-9]+\.[0-9]+)", _c35)
        check("the payload send_order builds carries a price at all (the stub was really called)",
              len(_prices35) >= 2, "%d price fields" % len(_prices35))
        check("...and every price in it fits inside the symbols digits",
              _prices35 and all(_dec35(x) <= _sm33.DIGITS["GBPUSD"] for x in _prices35),
              str(_prices35[:4]))
        check("the value that MT5 refused is nowhere in what is sent",
              "1.3165645839210065" not in _c35 and "1.310959999999999" not in _c35, "")
        check("volume is NOT reformatted — this is a digits fix, not a sizing one",
              '"volume\\":0.28' in _c35.replace("\\\\", "\\") or "0.28" in _c35, "")
        _jl35 = ""
        if os.path.exists(_sm33.JOURNAL_F):
            _jl35 = open(_sm33.JOURNAL_F).read()
        check("the journal line shows the number that was sent, not the raw float",
              "1.3165645839210065" not in _jl35 and ("1.31656" in _jl35 or not _jl35),
              _jl35[-120:].replace("\n", " "))
        # and the same call with the gate shut must not reach the terminal at all
        with open(os.path.join(_tmp35, "desk_mode.json"), "w") as _f35:
            _json35.dump({"entries_enabled": False}, _f35)
        _cap35.clear()
        _sm33.send_order(_st35, "GBPUSD", "sell stop", 0.28, 1.3165645839210065, 1.31957, 1.31096, "S21")
        check("with entries_enabled false nothing is sent, digits fixed or not",
              "cmd" not in _cap35, str(_cap35)[:90])
    finally:
        _sm33.STATE_F, _sm33.mac, _sm33.JOURNAL_F = _old_state35, _old_mac35, _old_j35
        import shutil as _sh35
        _sh35.rmtree(_tmp35, ignore_errors=True)

    # the trail had the same bug in a different file: a hardcoded 5, right or wrong for one symbol only
    _src35 = open(_PROD33).read()
    check("no site still hardcodes five digits on a stop it sends",
          "round(new_sl, 5)" not in _src35 and "round(new_sl,5)" not in _src35, "")
    _i35 = _src35.index("def send_order")
    _j35 = _src35.index("def ", _i35 + 10)
    _body35 = _src35[_i35:_j35]
    # the raw template is written ABOVE the guard on purpose, so the anchor is where the template is
    # filled in, not where the placeholder appears: shape the price, then substitute, then call curl.
    check("the rounding happens once, after the entries gate and before the payload is filled in",
          0 < _body35.count("fmt_px(sym, price)") == 1
          and _body35.index("entries_enabled") < _body35.index("fmt_px(sym, price)")
          < _body35.index('.replace("__PRICE__"'),
          "count=%d" % _body35.count("fmt_px(sym, price)"))


# 36 — the 10015 that was NOT about digits.  The three probe calls below were run against his live
# terminal (127.0.0.1:22346) on 2026-11-18 at 23:38 KL and differ only in type and price; GBPUSD was
# trading about 1.3156.  They are the whole argument for the geometry gate, so they are pinned as
# measured and not re-derived: a sell stop above the market is refused, the same price as a sell
# limit or a buy stop is accepted, and a sell stop below the market is accepted.  What the build did
# with that for a week was retry the frozen level every cycle and print a broker error code.
print("\n== 36: a stop must sit beyond the market, a limit within it")
if _PROD33 is None:
    check("the producer is not next to the repo, so the geometry gate is checked on the Mac (skipped here)",
          True, "skipped: no sentry_mac.py")
else:
    _BID, _ASK = 1.31561, 1.31564          # the quoted spread at probe time
    _ok1, _w1 = _sm33.pending_geom("GBPUSD", "sell stop", 1.31656, 1.31957, 1.31096, _BID, _ASK)
    check("the exact level the terminal refused is refused here, with a reason",
          _ok1 is False and "10015" in _w1, _w1[:110])
    check("...and the reason names the cause the journal never did",
          "crossed" in _w1, _w1[:110])
    _ok2, _w2 = _sm33.pending_geom("GBPUSD", "sell stop", 1.31256, 1.31957, 1.30896, _BID, _ASK)
    check("a sell stop BELOW the market passes (the probe call the terminal answered retcode 0 Done)",
          _ok2 is True, _w2)
    _ok3, _w3 = _sm33.pending_geom("GBPUSD", "sell limit", 1.31656, 1.31957, 1.31096, _BID, _ASK)
    check("the same price as a SELL LIMIT passes (accepted by the terminal, retcode 0 Done)",
          _ok3 is True, _w3)
    _ok4, _w4 = _sm33.pending_geom("GBPUSD", "buy stop", 1.31656, 1.31355, 1.31957, _BID, _ASK)
    check("the same price as a BUY STOP passes (accepted by the terminal, retcode 0 Done)",
          _ok4 is True, _w4)
    check("a buy stop below the ask is refused, the mirror-image rule",
          _sm33.pending_geom("GBPUSD", "buy stop", 1.31256, 1.31000, 1.31957, _BID, _ASK)[0] is False, "")
    check("a stop on the wrong side of its own entry is refused",
          _sm33.pending_geom("GBPUSD", "sell stop", 1.31256, 1.31000, 1.30896, _BID, _ASK)[0] is False,
          "sl above a sell entry only; here sl is below it")
    check("a target on the wrong side of its own entry is refused",
          _sm33.pending_geom("GBPUSD", "sell stop", 1.31256, 1.31957, 1.31896, _BID, _ASK)[0] is False, "")
    # the gate must never be the reason a trade did not happen on a broken quote
    for _b, _a in ((0, 0), (None, None), ("x", "y"), (1.31561, 0)):
        check("no opinion when the market is not visible (bid %r ask %r) — never blocks a real signal"
              % (_b, _a),
              _sm33.pending_geom("GBPUSD", "sell stop", 1.31656, 1.31957, 1.31096, _b, _a)[0] is True, "")
    check("an order type that is not pending is nobody's business",
          _sm33.pending_geom("GBPUSD", "buy", 1.31656, 0, 0, _BID, _ASK)[0] is True, "")
    _src36 = open(_PROD33).read()
    _i36 = _src36.index("gok, gwhy = pending_geom(")
    check("the gate sits between the size report and the send, so a held level is never spent at the terminal",
          _src36.rindex("size_report(sym,", 0, _i36) < _i36 < _src36.index("send_order(state, sym, otype", _i36),
          "")
    check("a held level does NOT burn the day's fire key (if price pulls back the signal is live again)",
          "done.append(fkey)" not in _src36[_i36:_i36 + 1400], "")
    check("...and it journals once per level, not once per cycle (that is how 90 lines were born)",
          "_gkey not in _gseen" in _src36[_i36:_i36 + 1400], "")
    check("the hold is counted into state, so the desk can see candidates waiting on price",
          'state["geom_held"]' in _src36[_i36:_i36 + 1400], "")


# 37 — "rejected" has to mean rejected.  Every retcode below was taken from his own journal of
# 2026-11-18 (211 mentions of 10015, 19 of 10018, 10 of 10021, 6 of 10016, 6 of 10009 — counted, not
# remembered), and the shapes are what the two MCP calls actually answer: trade_check_pending_order
# wraps its verdict in "ok": true/false, trade_send_pending_order answers with a bare retcode.
print("\n== 37: the terminal's answer, read as what it says")
if _PROD33 is None:
    check("no producer next to the repo (skipped here)", True, "skipped: no sentry_mac.py")
else:
    import json as _j37

    def _wrap37(inner):
        return _j37.dumps({"jsonrpc": "2.0", "id": 4, "result": {"isError": False,
                                                                  "content": [{"type": "text",
                                                                               "text": inner}]}})

    _sendref = _wrap37(_j37.dumps({"retcode": 10015, "retcode_details": "Invalid price"}))
    check("the bare-retcode send reply is a refusal, not a shrug",
          _sm33.parse_send_result(_sendref)["rejected"] is True, "")
    check("...and its words survive into the reason",
          _sm33.parse_send_result(_sendref)["details"] == "Invalid price",
          repr(_sm33.parse_send_result(_sendref)["details"]))
    for _code, _name in ((10016, "Invalid stops"), (10018, "Trade disabled"), (10021, "No prices")):
        check("%d (%s) counts as a refusal too" % (_code, _name),
              _sm33.parse_send_result(_wrap37(_j37.dumps({"retcode": _code,
                                                           "retcode_details": _name})))["rejected"] is True, "")
    check("10009 with an order id is a success",
          _sm33.parse_send_result(_wrap37(_j37.dumps({"retcode": 10009, "order": 59401583524})))["ok"] is True, "")
    check("10008 with an order id is a success too (a placed pending order is not a failure)",
          _sm33.parse_send_result(_wrap37(_j37.dumps({"retcode": 10008, "order": 59401583525})))["ok"] is True,
          "the ticket, not the code, is what makes it real")
    check("an accepted reply with an id never becomes a refusal",
          _sm33.parse_send_result(_wrap37(_j37.dumps({"retcode": 10008, "order": 59401583525})))["rejected"] is False,
          "")
    check("a reply with no retcode at all stays unjudged (a margin answer is not an order answer)",
          _sm33.parse_send_result(_wrap37(_j37.dumps({"ok": True, "margin": 11.0, "currency": "USD"})))["rejected"]
          is False, "")
    check("empty output is not a rejection (it is an unreadable one — reconcile decides)",
          _sm33.parse_send_result("")["rejected"] is False
          and _sm33.parse_send_result("")["ok"] is False, "")
    check("the ok:false shape that was already handled still is",
          _sm33.parse_send_result(_wrap37(_j37.dumps({"ok": False, "result": {"retcode": 10015}})))["rejected"]
          is True, "")
    _src37 = open(_PROD33).read()
    _i37 = _src37.index('d["ok"] = (not d["rejected"])')
    check("the refusal rule sits before the ok rule, so ok can never be earned by a refused reply",
          _src37.rindex("d[\"retcode\"] not in (None, 0, SEND_OK_RETCODE)", 0, _i37) < _i37
          and _src37.count("not in (None, 0, SEND_OK_RETCODE)") == 1, "")


# 38 — the alert queue, measured before it was touched.  Asked "alerts queued?" on 2026-11-18 23:56 KL,
# the Mac said: alerts.outbox 200 lines (exactly the cap), oldest 11:08 the same day, newest 23:50, of
# the held lines 116 NOTE advisories vs 4 FILLs; alerts.sent.log 2 lines, BOTH of them a bridge-drain
# test dated 11-17 02:45; no gmail_smtp.json; no HERMES_ALERT_WEBHOOK in com.hermes.radar's environment
# (launchctl printed only PATH/XPC_SERVICE_NAME).  So nothing had ever been delivered off the laptop,
# every line was re-queued every 60 s, each pass re-notified all 200, and the trim threw the OLDEST away
# — which over a 13-hour backlog means the FILL lines were the ones being lost.  Three local fixes, no
# new secret, all three checked here against the shipped functions.
print("\n== 38: the alert queue drains, or says it is not draining")
_RP38 = _asset("trade_radar.py") or _asset("tools", "mac", "trade_radar.py") \
    or _asset("tools/mac/trade_radar.py")
if not _RP38:
    check("trade_radar.py is not next to the repo, so the queue checks run on the Mac (skipped here)",
          True, "skipped: no trade_radar.py")
else:
    import tempfile as _tf38, shutil as _sh38
    _d38 = _tf38.mkdtemp(prefix="q38")
    _rd = _load32("radar38", _RP38)
    _rd.BASE = _d38
    _rd.OUTBOX_F = os.path.join(_d38, "alerts.outbox")
    _rd.SENT_F = os.path.join(_d38, "alerts.sent.log")
    _rd.NOTED_F = os.path.join(_d38, "alerts.notified")
    _rd.DROPPED_F = os.path.join(_d38, "alerts.dropped")
    _rd.SMTP_F = os.path.join(_d38, "gmail_smtp.json")
    _rd.OUTBOX_CAP = 20            # small, so the overflow maths is readable

    def _mk38(n_note, n_fill):
        """Interleaved the way the real file is: advisories and FILLs arriving in no particular order."""
        out, i, j = [], 0, 0
        while i < n_note or j < n_fill:
            if i < n_note:
                out.append("11-18 12:%02d KL | NOTE — advisory %d over soft cap" % (i % 60, i)); i += 1
            if j < n_fill:
                out.append("11-18 09:%02d KL | FILL — EURUSD sell 0.25@1.09668 profit -1.5 | ticket %d"
                           % (j % 60, 59378751598 + j)); j += 1
        return out

    _l38, _dr38 = _rd.trim_outbox(_mk38(200, 50), 60)
    check("over the cap the advisories are what gets thrown, not the fills",
          len(_l38) == 60 and sum(1 for x in _l38 if " FILL " in x) == 50,
          "kept %d, fills %d" % (len(_l38), sum(1 for x in _l38 if " FILL " in x)))
    check("...and the drop is counted, not silent", _dr38 == 190, "dropped %d" % _dr38)
    _l38z, _dr38z = _rd.trim_outbox(_mk38(200, 50), 20)
    check("if the urgent lines alone overflow the cap, the noise goes entirely and the newest fills stay",
          len(_l38z) == 20 and all(" FILL " in x for x in _l38z) and _dr38z == 230,
          "kept %d, dropped %d" % (len(_l38z), _dr38z))
    check("kept lines stay in the order they arrived (a shuffled tail reads as a broken clock)",
          _l38 == sorted(_l38, key=lambda x: x.split(" KL | ")[0]), "")
    _l38b, _dr38b = _rd.trim_outbox(_mk38(0, 50), 20)
    check("when EVERYTHING is important it keeps the newest, and still says how many went",
          len(_l38b) == 20 and _dr38b == 30
          and "ticket 59378751647" in _l38b[-1] and "ticket 59378751598" not in "".join(_l38b),
          _l38b[-1][-28:])
    _l38c, _dr38c = _rd.trim_outbox(_mk38(5, 2), 20)
    check("under the cap it is the identity — no reordering, no counting",
          _l38c == _mk38(5, 2) and _dr38c == 0, "")
    check("the tag test reads through the timestamp stamp, not the whole line",
          _rd.is_urgent("11-18 23:49 KL | CHECK/SEND FAILED NVDA sell stop: retcode 10015")
          and not _rd.is_urgent("11-18 23:49 KL | NOTE — GBPUSD theme exposure over soft cap"), "")
    check("a crypto line counts as urgent even though its tag is a bracket",
          _rd.is_urgent("11-18 23:50 KL | [CRYPTO/crypto] FILL — AVAX/USD S4-band-fade-long 1008@6.963"), "")

    # the flush itself: stub the terminal-side channels, leave the logic shipped
    _pings = []
    _rd.mac_notify = lambda title, text: _pings.append(text)
    _rd.send_webhook = lambda line: None
    _q38 = _mk38(3, 1)
    with open(_rd.OUTBOX_F, "w") as _f38:
        _f38.write("\n".join(_q38) + "\n")
    _rd.flush_outbox()
    _after1 = [l.rstrip("\n") for l in open(_rd.OUTBOX_F) if l.strip()]
    check("with no channel configured a line stays QUEUED — it is never dropped to look tidy",
          len(_after1) == 4 and os.path.exists(_rd.SENT_F) is False, str(len(_after1)))
    check("each line is announced exactly once per flush cycle", len(_pings) == 4, "%d pings" % len(_pings))
    _rd.flush_outbox()
    _rd.flush_outbox()
    check("...and NOT once a minute forever (this is the 200-ping bug: 3 flushes, still 4 notifications)",
          len(_pings) == 4, "%d pings after 3 flushes" % len(_pings))
    with open(_rd.OUTBOX_F, "a") as _f38:
        _f38.write("11-18 23:58 KL | FILL — GBPUSD buy 0.26@1.31660 profit 2.1 | ticket 59402000001\n")
    _rd.flush_outbox()
    check("a genuinely NEW event still notifies immediately, watermark or not", len(_pings) == 5,
          "%d pings" % len(_pings))
    _rd.send_webhook = lambda line: True
    _rd.flush_outbox()
    check("once something off the Mac accepts it, it leaves the queue and is journalled as sent",
          os.path.exists(_rd.OUTBOX_F) and not [l for l in open(_rd.OUTBOX_F) if l.strip()]
          and sum(1 for l in open(_rd.SENT_F) if l.strip()) == 5, "")
    # The cap is read from the module at flush time, not bound at import — so this overflow can be
    # sized against the small cap the pure trim calls above used: 24 advisories plus 4 fills, cap 20.
    with open(_rd.OUTBOX_F, "w") as _f38:
        _f38.write("\n".join(_mk38(24, 4)) + "\n")
    _rd.send_webhook = lambda line: None
    _rd.OUTBOX_CAP = 20
    _rd.flush_outbox()
    _ov = [l.rstrip("\n") for l in open(_rd.OUTBOX_F) if l.strip()]
    check("an overflowing queue keeps its fills and reports the loss",
          len(_ov) == 20 and sum(1 for x in _ov if " FILL " in x) == 4 and _rd._read_dropped() > 0,
          "held %d, dropped %d" % (len(_ov), _rd._read_dropped()))
    # Read the constant back out of the source: _rd.OUTBOX_CAP has been set to 20 by the overflow test
    # above, so the module attribute can no longer tell us what ships.  The file is the only witness.
    _snip0 = open(_RP38).read()
    _code0 = "\n".join(l for l in _snip0.splitlines() if not l.lstrip().startswith("#"))
    _cap_src38 = _re35.search(r"^OUTBOX_CAP = (\d+)", _code0, _re35.M)
    # prose is allowed to QUOTE the old literal — that is what the comment above the constant is for —
    # so the "the bare number is gone" half is measured against the code lines only.  A check that
    # failed on its own explanation is a check that trains you to distrust it.
    check("the cap is one named constant, read at flush time (nothing else in the file assumes a value)",
          "trim_outbox(remaining, OUTBOX_CAP)" in _code0 and "remaining[-200:]" not in _code0,
          "literal still in code" if "remaining[-200:]" in _code0 else "call site does not pass the cap")
    check("the shipped retention is a decision, not the inherited literal 200",
          _cap_src38 is not None and int(_cap_src38.group(1)) >= 2000,
          "OUTBOX_CAP = %s" % (_cap_src38.group(1) if _cap_src38 else "?"))
    check("the notify watermark tracks the cap, so a bigger spool cannot re-ping old lines",
          "[-OUTBOX_CAP:]" in _snip0, "")
    _snip0 = open(_RP38).read()
    check("the queue's state is published, not just logged: cap, urgent held, dropped, full",
          all(k in _snip0 for k in ('"cap": OUTBOX_CAP', '"urgent_held"', '"dropped": _read_dropped()',
                                   '"full": len(_ob) >= OUTBOX_CAP')), "")
    check("and the page prints it as queued/CAP plus a dropped count, so a stuck queue is visible on the phone",
          "d.channels.queued+'/'+" in _snip0 and "' held, '" in _snip0, "")
    _sh38.rmtree(_d38, ignore_errors=True)

print("\n%d checks failed" % len(FAILS))
sys.exit(1 if FAILS else 0)