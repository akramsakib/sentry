"""Functional check, through the REAL run_cycle.run(), that the desk's entries switch sends nothing
when it is off — and, in the SAME harness with the switch on, that it sends something.

Why both halves: "zero orders placed" is only evidence if the same run can place one. A probe that
only ever sees zeros passes when the scan produced no candidates at all, when the fee guard refused
everything, or when the harness mis-stubbed the broker — which is how a kill switch ends up "tested"
and actually be a no-op. So: control first (switch ON ⇒ ≥1 place_order), then the hold (switch OFF ⇒
0 place_order, and the candidate still journalled as HELD so the graded record keeps growing).

    python3 tools/checks/check_held_entries.py

No network: the broker in this folder's config gets its call sites stubbed, bars are synthetic (a
downtrend ending in a hammer, which is one of the §12 patterns this book scans for), and place_order
only appends to a list.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CODE = ["run_cycle.py", "sentry_core.py", "broker_okx.py", "broker_bitget.py",
        "broker_coinbase.py", "broker_ledger.py", "config.json"]

PROBE = r'''
import datetime, json, os, sys, time
sys.path.insert(0, DIR)
os.chdir(DIR)
for k in ("BITGET_DRY", "OKX_SIM", "BITGET_SIM", "COINBASE_DRY", "COINBASE_MODE", "SENTRY_FIXTURES"):
    os.environ.pop(k, None)
for k in ("BITGET_API_KEY", "BITGET_API_SECRET", "BITGET_API_PASSPHRASE",
          "OKX_API_KEY", "OKX_API_SECRET", "OKX_API_PASSPHRASE", "COINBASE_API_KEY"):
    os.environ[k] = "stub"
import run_cycle as rc

MODE = MODE_HERE
if MODE is not None:                                  # write the switch file into this folder
    json.dump(MODE, open(os.path.join(DIR, "crypto_desk_mode.json"), "w"))
    rc.HOLD_F = "crypto_desk_mode.json"

cfg = json.load(open(os.path.join(DIR, "config.json")))
# live_gate needs all four of these to be happy; without them the scan never runs and the whole
# probe measures nothing. They are set on the loaded config, not the file, so the release is untouched.
rc.CFG["live_ack"] = True
rc.CFG["min_grade_before_live"] = 1
rc.CFG["max_gap_h"] = 24.0
venue = cfg.get("execution", "okx")
B = rc.broker
sent = []


def _bars(sym, tf, limit):
    """Synthetic downtrend ending in a hammer/takuri bar, same shape/keys a real venue returns."""
    step = {"5Minute": 300, "15Minute": 900, "1Hour": 3600, "4Hour": 14400, "1Day": 86400}[tf]
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp() // step * step)
    px0 = 200.0
    out = []
    n = max(6, min(limit, 120))
    for i in range(n):
        px = px0 - i * (px0 * 0.002)                  # steady grind down
        t = datetime.datetime.fromtimestamp(now - step * (n - i), datetime.timezone.utc)
        out.append({"t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": px * 1.002, "h": px * 1.006,
                    "l": px * 0.997, "c": px, "v": 10.0 + i})
    t = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
    low_c = out[-1]["c"]
    out.append({"t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": low_c * 0.999, "h": low_c * 1.002,
                "l": low_c * 0.972, "c": low_c * 1.0005, "v": 90.0})   # long lower wick, small body
    while len(out) < limit:
        out.insert(0, dict(out[0]))
    return out


def _place(*args, **kw):
    # real place_order(side, symbol, qty=..., otype=..., ...) — positional, so capture both halves
    d = {"side": args[0] if args else kw.get("side"), "symbol": args[1] if len(args) > 1 else kw.get("symbol")}
    d.update({k: kw.get(k) for k in ("otype", "qty", "stop_price", "limit_price")})
    sent.append(d)
    return {"ok": True, "id": "stub-1"}


B.account = lambda *a, **k: {"equity": 40000.0, "cash": 40000.0, "available": 40000.0, "raw": {}}
B.positions = lambda *a, **k: []
B.open_orders = lambda *a, **k: []
B.order_by_cid = lambda *a, **k: None
B.fills = lambda *a, **k: []
B.cancel_order = lambda *a, **k: True
B.cancel_for = lambda *a, **k: []
B.crypto_bars = _bars
B.place_order = _place
B.BrokerError = getattr(B, "BrokerError", Exception)
rc.MONEY = True
rc.LIVE = True

print("  venue:", venue, "| MONEY:", rc.MONEY, "| switch:", MODE)
rc.run()
print("  rc.HOLD after run:", rc.HOLD, "|", rc.HOLD_WHY)
j = open(os.path.join(DIR, "journal.md")).read()
held = [l for l in j.splitlines() if "HELD —" in l]
sentlines = [l for l in j.splitlines() if "ORDER SENT" in l or "DRY-FIRE" in l or "LIVE ORDER" in l]
print("  place_order calls:", len(sent))
print("  HELD lines      :", len(held), (held[-1].split("**")[-1].strip()[:150] if held else ""))
print("  sent lines      :", len(sentlines), (sentlines[-1].split("**")[-1].strip()[:150] if sentlines else ""))
if MODE == {"entries_enabled": False, "why": "probe hold"}:
    ok = (rc.HOLD and not sent and held and len(sentlines) == 0)
else:
    ok = (not rc.HOLD and len(sent) >= 1)
print("  candidates seen in log:", len([1 for l in open(os.path.join(DIR, "trades_log.jsonl"))
                                        if '"fired"' in l]))
print("RESULT:", "PASS" if ok else "FAIL")
'''


def run_pass(d, mode, label):
    """Each pass starts from a CLEAN book: state, ledger and journal are rebuilt, because a pass that
    inherits the control run's pendings would skip every candidate as "already in play" and report a
    vacuous PASS for the hold."""
    for f in ("journal.md", "state.json", "ledger.json", "crypto_desk_mode.json"):
        p = os.path.join(d, f)
        if os.path.exists(p):
            os.remove(p)
    open(os.path.join(d, "journal.md"), "w").close()
    json.dump({"orders": [], "seen_candles": [], "last_cycle": time.time(),
               "pos_state": {}, "open_cids": {}, "cid_seq": 0, "fired_today": []},
              open(os.path.join(d, "state.json"), "w"))
    json.dump({"cash": 100000.0, "realized": 0.0, "fees_paid": 0.0, "orders": [], "positions": []},
              open(os.path.join(d, "ledger.json"), "w"))
    probe = PROBE.replace("DIR", repr(d)).replace("MODE_HERE", repr(mode))
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=600)
    out = (r.stdout or "").strip()
    print(f"--- {label} ---")
    print(out or "(no stdout)")
    if r.returncode != 0:
        print("   probe exited", r.returncode, "\n", (r.stderr or "")[-1200:])
    return "RESULT: PASS" in out, out


def main():
    root = os.environ.get("CHECK_BOOK_DIR") or HERE
    d = tempfile.mkdtemp(prefix="held-entries-")
    try:
        for f in CODE:
            src = os.path.join(root, f)
            if not os.path.exists(src):
                src = os.path.join(HERE, f)
            shutil.copy(src, os.path.join(d, os.path.basename(f)))
        # a graded past, so live_gate is satisfied and the scan really runs
        with open(os.path.join(d, "trades_log.jsonl"), "w") as f:
            for i in range(6):
                f.write(json.dumps({"rid": f"H{i}", "sym": "BTC/USD", "skill": "S18-ma-revert-long",
                                    "otype": "buy_stop", "entry": 100.0, "sl": 99.5, "tp": 101.5,
                                    "score": 3, "risk": 25.0, "fired": True, "result": "win",
                                    "R": 0.6, "note": "probe history"}) + "\n")
        ctrl, _ = run_pass(d, None, "control — switch absent, entries must be placed")
        held_ok, held_out = run_pass(d, {"entries_enabled": False, "why": "probe hold"},
                                "hold — switch off, nothing may be placed")
        both = run_pass(d, {"entries_enabled": True}, "switch explicitly on = same as absent")
        # the hold pass already requires "place_order calls: 0" inside its own RESULT; here we only
        # require all three halves, with the control's sends as the evidence that a zero means pause.
        ok = bool(ctrl) and bool(held_ok) and bool(both[0])
        print("switch-off stdout says:", [l.strip() for l in held_out.splitlines()
                                            if "place_order calls" in l][:1], "|| switch-on says:",
              "see control above")
        print(f"\norders placed with the switch off vs on: "
              f"{'0 (held)' if held_ok else 'FAIL'} vs {'>=1 (control)' if ctrl else 'FAIL'}")
        print("RESULT:", "PASS" if ok else "FAIL")
        shutil.rmtree(d, ignore_errors=True)
        return 0 if ok else 1
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise


if __name__ == "__main__":
    sys.exit(main())
