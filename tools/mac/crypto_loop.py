#!/usr/bin/env python3
"""Sentry CRYPTO (Mac-native) — the resident parity engine, real money on OKX.

Same code as the GitHub build (sentry_core/run_cycle/broker_okx at v4.7.2) living on this Mac
the way the MT5 forex build does: one cycle every CRYPTO_CYCLE seconds, its own state folder,
its own alerts into the hermes desk channel. No MT5, no Wine, no GitHub cron — OKX REST only,
24/7, five timeframes, the full Mac skill array (22 §12 patterns + 16 families).

Keys, when they exist, live ONLY in ./okx.env (or ./coinbase.env + ./coinbase.pem for the Coinbase
lane), chmod 600, and nowhere else: not in this folder's journal, not on GitHub. To arm real money:
    1. uncomment the key lines in the env file that matches config.json's "execution" value
    2. launchctl kickstart -k gui/$(id -u)/com.hermes.sentry.crypto
Kill switches: blank the env values (next cycle falls back to shadow, never to half-sent),
or `launchctl bootout gui/$(id -u)/com.hermes.sentry.crypto` — venue-side TP/SL still protect
whatever is open.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
sys.path.insert(0, HERE)

# Two lanes, two key files, loaded in this order. okx.env holds OKX_API_KEY/SECRET/PASSPHRASE;
# coinbase.env holds COINBASE_API_KEY + either COINBASE_API_SECRET+COINBASE_API_PASSPHRASE
# (Exchange, institutional host) or nothing if the retail CDP private key sits in ./coinbase.pem.
# Whichever file is EMPTY is the lane that stays on the shadow ledger — so an OKX-armed folder with
# no coinbase.env simply ignores the Coinbase branch, and vice versa. chmod 600 on all three.
for ENVF in (os.path.join(HERE, "okx.env"), os.path.join(HERE, "coinbase.env")):
    if not os.path.exists(ENVF):
        continue
    for _line in open(ENVF):
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))
_pem = os.path.join(HERE, "coinbase.pem")
if os.path.exists(_pem):                                   # retail CDP keys are a PEM blob, not an env line
    os.environ.setdefault("COINBASE_CDP_PEM", open(_pem).read())   # the adapter wants the TEXT (openssl)

import run_cycle as rc                                        # noqa: E402

JOURNAL = os.path.join(HERE, "journal.md")
OUTBOX = os.path.join(HERE, "alerts.outbox")
CYCLE = int(os.environ.get("CRYPTO_CYCLE", "300"))
URGENT = ("ORDER SENT", "FILL", "CLOSED", "LIVE ACK", "ALERT", "REAL MONEY", "SCRATCH")
_last_wake = [0.0]


def kl_stamp():
    return time.strftime("%m-%d %H:%M KL", time.gmtime(time.time() + 8 * 3600))


def alert(msg, urgent=False):
    """Outbox first (same file shape the forex build writes), then the desk wake-wire."""
    try:
        with open(OUTBOX, "a") as f:
            f.write(f"{kl_stamp()} | [CRYPTO] {msg}\n")
    except Exception:
        pass
    if not urgent:
        return
    if time.time() - _last_wake[0] < 180:
        return
    _last_wake[0] = time.time()
    import json
    import subprocess
    try:
        payload = json.dumps({"prompt": "[DESK-WAKE] [CRYPTO] " + msg[:700]
                                       + " | Arena desk: crypto-book event, handle per playbook."})
        subprocess.run(["curl", "-sS", "--max-time", "20", "-X", "POST",
                        "http://127.0.0.1:8768/ask", "-H", "Content-Type: application/json",
                        "-d", payload], capture_output=True, timeout=30)
    except Exception:
        pass


def _journal_lines():
    try:
        return open(JOURNAL).read().splitlines()
    except Exception:
        return []


def run_once():
    before = len(_journal_lines())
    try:
        rc.run()
    except SystemExit:
        pass                                # rc.fail() journalled the ALERT already; keep the loop alive
    except Exception as e:                  # noqa: BLE001
        rc.journal(f"ALERT — crypto cycle crashed: {type(e).__name__}: {e}")
    for line in _journal_lines()[before:]:
        body = line.split("**", 2)[-1].strip() if "**" in line else line
        if any(p in body for p in URGENT):
            alert(body[:400], urgent=True)
    try:                                    # rotate instead of growing forever
        if os.path.exists(JOURNAL) and os.path.getsize(JOURNAL) > 512 * 1024:
            os.replace(JOURNAL, JOURNAL + ".1")
    except Exception:
        pass


if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once()
        print("crypto_loop: single cycle done (verify mode)", flush=True)
        sys.exit(0)
    _exe = getattr(rc, "EXEC_MODE", "?")
    _keyf = "./okx.env" if _exe == "okx" else ("./coinbase.env + ./coinbase.pem" if _exe == "coinbase" else "./env files")
    if not os.environ.get("OKX_API_KEY") and not os.environ.get("COINBASE_API_KEY"):
        _keyf += " (both empty → shadow ledger, nothing is sent)"
    rc.journal(f"crypto_loop: resident on this Mac — cycle every {CYCLE}s · venue per config ({_exe}) · "
               f"keys from {_keyf} · this is the ONLY armed book for its account "
               f"(the repo mirror ships auto_ack off)")
    while True:
        run_once()
        time.sleep(CYCLE)
