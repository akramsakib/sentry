"""Functional proof, through the REAL run_cycle.run(), that an ARMED venue account with $0 in it
sends nothing.

Run it directly:  python3 tools/check_empty_wallet.py

Nothing is asked of the venue: broker._req is replaced with a stub that answers the wallet as
`{"data": {"equity": "0"}}` and records every attempt to place an order, and rc.fetch_bars is
replaced with synthetic flat bars. So this exercises the shipped gate, not a copy of it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

SRC = os.path.abspath(os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")))
CODE = ["run_cycle.py", "sentry_core.py", "broker_bitget.py", "broker_okx.py",
        "broker_ledger.py", "broker_coinbase.py"]

PROBE = r'''
import json, os, sys, datetime
sys.path.insert(0, DIR)
os.chdir(DIR)
for k in ("BITGET_DRY", "OKX_SIM", "BITGET_SIM", "COINBASE_DRY"):
    os.environ.pop(k, None)
os.environ["BITGET_API_KEY"] = "test-key"; os.environ["BITGET_API_SECRET"] = "s"; os.environ["BITGET_API_PASSPHRASE"] = "p"
import broker_bitget as bg
import run_cycle as rc

sent = []
def fake_req(method, path, body=None, auth=True):
    if path.endswith("/accounts"):
        return {"data": [{"equity": "0", "usdtEquity": "0", "available": "0",
                          "crossMaxAvailable": "0", "fixedMaxAvailable": "0", "crossAvailableEquity": "0"}]}
    if path.endswith("/positions"):
        return {"data": []}
    if "order" in path:
        sent.append((method, path, body))
        return {"data": {"orderId": "FAKE"}}
    return {"data": {}}
bg._req = fake_req
bg.account = lambda: {"equity": 0.0, "cash": 0.0, "raw": {}}
bg.positions = lambda: []
bg.open_orders = lambda: []
bg.fills = lambda *a, **k: []
bg.cancel_order = lambda *a, **k: True

def bars(sym):
    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp() // 3600 * 3600)
    out = {}
    for tf, step in (("5m", 300), ("15m", 900), ("1h", 3600), ("4h", 14400), ("1d", 86400)):
        rows = []
        for i in range(60):
            px = 100.0 + i * 0.01
            rows.append({"t": datetime.datetime.utcfromtimestamp(now - step * (60 - i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "o": px, "h": px * 1.001, "l": px * 0.999, "c": px, "v": 10.0})
        out[tf] = rows
    return out, False
rc.fetch_bars = bars
rc.live_positions = lambda: []

print("  MONEY:", rc.MONEY, "LIVE:", rc.LIVE, "venue:", rc.VENUE)
rc.run()
j = open(os.path.join(DIR, "journal.md")).read()
line = [l for l in j.splitlines() if "equity" in l and "ALERT" in l]
print("  ALERT line:", (line[-1].split("**")[-1].strip() if line else "NONE"))
print("  orders attempted against the venue:", len(sent))
ok = bool(line) and not sent and "No new entries" in (line[-1] if line else "")
print("RESULT:", "PASS" if ok else "FAIL")
'''

d = tempfile.mkdtemp()
for f in CODE:
    shutil.copy(os.path.join(SRC, f), os.path.join(d, f))
cfg = json.load(open(os.path.join(SRC, "config.json")))
cfg["execution"] = "bitget"
cfg["fees"] = {"maker": 0.0002, "taker": 0.0006}
cfg["auto_ack_on_key"] = True
cfg["symbols"] = ["BTC/USD"]
json.dump(cfg, open(os.path.join(d, "config.json"), "w"), indent=2)
open(os.path.join(d, "journal.md"), "w").close()
open(os.path.join(d, "state.json"), "w").write('{"orders":[],"seen_candles":[]}')
open(os.path.join(d, "ledger.json"), "w").write(
    '{"cash":100000.0,"realized":0.0,"fees_paid":0.0,"orders":[],"positions":[]}')
probe = PROBE.replace("DIR", repr(d))
r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=300)
print(r.stdout.strip() or ("STDOUT EMPTY"), "\n" + (r.stderr[-1200:] if r.returncode else ""))
if "--keep" not in sys.argv:
    shutil.rmtree(d, ignore_errors=True)
else:
    print("kept:", d)
