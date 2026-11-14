"""Functional check, through the REAL run_cycle.run(), that a $10 account is refused by the old
25 %-of-equity notional cap and IS sized correctly by the leverage cap — and that the leverage cap still
refuses an absurd size.

Why: `max_notional_frac: 0.25` (a spot-book rule) and a 0.5 % stop with risk capped at 1 % of equity are
mutually unsatisfiable — 0.01 ÷ 0.005 = 2.0x equity of notional, at every account size — so the shipped
guards refused every signal below ~$20k. That made the whole build a toy for a real small deposit while
looking like caution. `max_leverage` says the same bound in perp units and replaces the fraction.

    python3 tools/checks/check_small_account.py            # both passes
    CHECK_BOOK_DIR=~/hermes_sentry/crypto-bitget python3 tools/checks/check_small_account.py

No network, no money: the broker in the folder's config gets its call sites stubbed, bars are synthetic,
and place_order only appends to a list. The equity being $10 is a number in a stub, nothing more.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

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
cfgp = os.path.join(DIR, "config.json")
cfg = json.load(open(cfgp))
cfg.update(EDITS)                      # what differs between the passes; the file is recopied each time
json.dump(cfg, open(cfgp, "w"), indent=2)
import run_cycle as rc
rc.CFG["live_ack"] = True
rc.CFG["min_grade_before_live"] = 0
rc.CFG["max_gap_h"] = 24.0
B = rc.broker
sent = []
EQ = 10.0


def _bars(sym, tf, limit):
    step = {"5Minute": 300, "15Minute": 900, "1Hour": 3600, "4Hour": 14400, "1Day": 86400}[tf]
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp() // step * step)
    px0, out = 200.0, []
    n = max(6, min(limit, 120))
    for i in range(n):
        px = px0 - i * (px0 * 0.002)
        t = datetime.datetime.fromtimestamp(now - step * (n - i), datetime.timezone.utc)
        out.append({"t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": px * 1.002, "h": px * 1.006,
                    "l": px * 0.997, "c": px, "v": 10.0 + i})
    t = datetime.datetime.fromtimestamp(now, datetime.timezone.utc)
    lc = out[-1]["c"]
    out.append({"t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": lc * 0.999, "h": lc * 1.002,
                "l": lc * 0.972, "c": lc * 1.0005, "v": 90.0})
    while len(out) < limit:
        out.insert(0, dict(out[0]))
    return out


def _place(*a, **kw):
    d = {"side": a[0] if a else kw.get("side"), "symbol": a[1] if len(a) > 1 else kw.get("symbol")}
    d.update({k: kw.get(k) for k in ("otype", "qty", "stop_price", "limit_price")})
    sent.append(d)
    return {"ok": True, "id": "stub-1"}


B.account = lambda *a, **k: {"equity": EQ, "cash": EQ, "available": EQ, "raw": {}}
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

print("  config:", {k: cfg.get(k) for k in ("max_notional_frac", "max_leverage", "min_notional",
                                            "live_max_risk", "live_max_risk_frac")})
nf, words = rc.notional_cap(cfg)
print("  notional_cap() ->", nf, "|", words)
rc.run()
j = open(os.path.join(DIR, "journal.md")).read()
lines = j.splitlines()
cap_skips = [l for l in lines if "SKIP" in l and "Cap is" in l]
sizes = []
for d in sent:
    px = d.get("limit_price") or d.get("stop_price") or 0
    sizes.append(round((px or 0) * (d.get("qty") or 0), 4))
print("  orders attempted:", len(sent), "| notionals:", sizes[:4])
print("  cap refusals   :", len(cap_skips), (cap_skips[-1].split("**")[-1].strip()[:170] if cap_skips else ""))
min_not = [l for l in lines if "below min notional" in l]
print("  venue-min refusals:", len(min_not))
if MODE == "tight":                 # an absurd cap must bind, and say which cap it is
    ok = not sent and cap_skips and "Cap is 0% of equity" in cap_skips[-1]
elif MODE == "lev":                 # max_leverage replaces the frac cap: that reason must disappear
    ok = not cap_skips and nf == float(cfg.get("max_leverage")) and not sent and len(min_not) >= 1
else:                               # "free": with the venue floor lifted, a $10 account DOES size an order
    ok = (len(sent) >= 1 and all(0 < n <= 3 * EQ for n in sizes) and not cap_skips
          and any("1% of equity" in l for l in lines))
print("RESULT:", "PASS" if ok else "FAIL")
'''


def run_pass(d, edits, mode, label):
    for f in ("journal.md", "state.json", "ledger.json", "trades_log.jsonl",
              "crypto_desk_mode.json", "crypto_desk_mode.json"):
        p = os.path.join(d, f)
        if os.path.exists(p):
            os.remove(p)
    open(os.path.join(d, "journal.md"), "w").close()
    json.dump({"orders": [], "seen_candles": [], "last_cycle": __import__("time").time(),
               "pos_state": {}, "open_cids": {}, "cid_seq": 0, "fired_today": []},
              open(os.path.join(d, "state.json"), "w"))
    json.dump({"cash": 10.0, "realized": 0.0, "fees_paid": 0.0, "orders": [], "positions": []},
              open(os.path.join(d, "ledger.json"), "w"))
    probe = (PROBE.replace("DIR", repr(d)).replace("EDITS", repr(edits)).replace("MODE", repr(mode)))
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=600)
    out = (r.stdout or "").strip()
    print(f"--- {label} ---")
    print(out or "(no stdout)")
    if r.returncode:
        print("   exited", r.returncode, "\n", (r.stderr or "")[-900:])
    return "RESULT: PASS" in out, out


def main():
    root = os.environ.get("CHECK_BOOK_DIR") or HERE
    d = tempfile.mkdtemp(prefix="small-acct-")
    try:
        for f in CODE:
            src = os.path.join(root, f)
            if not os.path.exists(src):
                src = os.path.join(HERE, f)
            shutil.copy(src, os.path.join(d, os.path.basename(f)))
        # the probe WRITES config.json inside the temp copy, so every pass must recopy from source or
        # pass A's absurd cap silently leaks into B and C and the comparison means nothing.
        shutil.copy(os.path.join(root, "config.json") if os.path.exists(os.path.join(root, "config.json"))
                    else os.path.join(HERE, "config.json"), os.path.join(d, "config.json"))
        a, _ = run_pass(d, {"min_notional": 5.0, "max_notional_frac": 0.0001}, "tight",
                        "A — a deliberately absurd notional cap must bind and name itself")
        b, ob = run_pass(d, {"min_notional": 5.0, "max_notional_frac": 0.25, "max_leverage": 3.0},
                         "lev", "B — max_leverage 3.0 replaces the 25 % frac cap on the same $10 account")
        c, oc = run_pass(d, {"min_notional": 0.0, "max_notional_frac": 0.25, "max_leverage": 3.0},
                         "free", "C — with the venue's own $5 floor lifted, $10 sizes a real order")
        for tag, out in (("B", ob), ("C", oc)):
            for l in out.splitlines():
                if "orders attempted" in l or "notional_cap()" in l:
                    print(f"   [{tag}] {l.strip()}")
        print("RESULT:", "PASS" if (a and b and c) else "FAIL")
        shutil.rmtree(d, ignore_errors=True)
        return 0 if (a and b and c) else 1
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise


if __name__ == "__main__":
    sys.exit(main())
