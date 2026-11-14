"""Functional check, through the REAL run_cycle.run(), that an ARMED venue account with $0 in it
sends nothing — whatever the venue in that folder's config is.

Why this exists: `equity = float((acct or {}).get("equity") or 100000.0)` treated a genuine `0.0` as a
missing value, so an armed-but-unfunded account (the normal state on key day) was sized against the
$100,000 shadow wallet. The book would then keep trying to send orders into an empty margin account,
and the journal's `equity $100,000` line would read as if the check had passed. `venue_equity()` fixes
it; this file proves the fix by driving the whole cycle, not a copy of the arithmetic.

Run it from a book folder or the repo root:
    python3 tools/checks/check_empty_wallet.py
It touches no network: the broker the folder's config names gets its nine call sites stubbed, and the
wallet stub says zero on purpose. Nothing can leave the machine from here — place_order only records.
"""
import datetime
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
import datetime, json, os, sys
sys.path.insert(0, DIR)
os.chdir(DIR)
for k in ("BITGET_DRY", "OKX_SIM", "BITGET_SIM", "COINBASE_DRY", "COINBASE_MODE", "SENTRY_FIXTURES"):
    os.environ.pop(k, None)
# one non-empty key trio is enough to arm whichever lane the config names; the others stay unset so
# the venue actually chosen for this book is the one being tested.
for k in ("BITGET_API_KEY", "BITGET_API_SECRET", "BITGET_API_PASSPHRASE",
          "OKX_API_KEY", "OKX_API_SECRET", "OKX_API_PASSPHRASE", "COINBASE_API_KEY"):
    os.environ[k] = "stub"
import run_cycle as rc

cfg = json.load(open(os.path.join(DIR, "config.json")))
venue = cfg.get("execution", "okx")
B = rc.broker
sent = []


def _bars(sym, tf, limit):
    """Same shape every broker's crypto_bars returns: dicts, oldest→newest, t as an ISO string.

    (A list-of-lists here dies inside fetch_bars, which is a useful accident: it proves fetch_bars is
    really being exercised rather than skipped.)
    """
    step = {"5Minute": 300, "15Minute": 900, "1Hour": 3600, "4Hour": 14400, "1Day": 86400}[tf]
    # each timeframe aligned to ITS OWN period, newest bar one step back: floor everything to the top
    # of the hour and the last 5m bar looks 55 minutes stale, which trips the feed-age guard before
    # the wallet check is ever reached (it did, on the first run of this file).
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp() // step * step)
    out = []
    for i in range(limit):
        px = 100.0 + i * 0.01
        t = datetime.datetime.fromtimestamp(now - step * (limit - i), datetime.timezone.utc)
        out.append({"t": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "o": px, "h": px * 1.001,
                    "l": px * 0.999, "c": px, "v": 10.0})
    return out


def _place(**kw):
    sent.append(kw)
    raise AssertionError("place_order was reached on a $0 account — the gate did not fire")


B.account = lambda *a, **k: {"equity": 0.0, "cash": 0.0, "available": 0.0, "raw": {}}
B.positions = lambda *a, **k: []
B.open_orders = lambda *a, **k: []
B.order_by_cid = lambda *a, **k: None
B.fills = lambda *a, **k: []
B.cancel_order = lambda *a, **k: True
B.cancel_for = lambda *a, **k: []
B.crypto_bars = _bars
B.place_order = _place
B.BrokerError = getattr(B, "BrokerError", Exception)
rc.MONEY = True                      # a real wallet, a real venue: no DRY, no SIM
rc.LIVE = True

print("  venue:", venue, "| MONEY:", rc.MONEY, "| broker:", B.__name__)
rc.run()
j = open(os.path.join(DIR, "journal.md")).read()
alerts = [l for l in j.splitlines() if "ALERT" in l and "equity" in l]
scan = [l for l in j.splitlines() if "scan ok" in l]
print("  alert:", (alerts[-1].split("**")[-1].strip() if alerts else "NONE"))
print("  scan :", (scan[-1].split("**")[-1].strip() if scan else "NONE"))
print("  orders attempted:", len(sent))
ok = (bool(alerts) and not sent and "No new entries" in alerts[-1]
      and "equity $0.00" in (scan[-1] if scan else ""))
print("RESULT:", "PASS" if ok else "FAIL")
'''


def main():
    root = os.environ.get("CHECK_BOOK_DIR") or HERE
    d = tempfile.mkdtemp(prefix="empty-wallet-")
    for f in CODE:
        src = os.path.join(root, f)
        if not os.path.exists(src):
            src = os.path.join(HERE, f)
        shutil.copy(src, os.path.join(d, os.path.basename(f)))
    for f in ("journal.md",):
        open(os.path.join(d, f), "w").close()
    open(os.path.join(d, "state.json"), "w").write('{"orders":[],"seen_candles":[]}')
    open(os.path.join(d, "ledger.json"), "w").write(
        '{"cash":100000.0,"realized":0.0,"fees_paid":0.0,"orders":[],"positions":[]}')
    probe = PROBE.replace("DIR", repr(d))
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=300)
    shutil.rmtree(d, ignore_errors=True)
    print((r.stdout or "").strip())
    if r.returncode != 0:
        print("probe exited", r.returncode, "\n", (r.stderr or "")[-900:])
    return 0 if "RESULT: PASS" in (r.stdout or "") else 1


if __name__ == "__main__":
    sys.exit(main())
