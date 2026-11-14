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

# One key file per lane, all loaded, alphabetically: okx.env (OKX_API_KEY/SECRET/PASSPHRASE),
# coinbase.env (COINBASE_API_KEY + either COINBASE_API_SECRET+COINBASE_API_PASSPHRASE for the
# Exchange host, or nothing if the retail CDP private key sits in ./coinbase.pem), and
# bitget.env (BITGET_API_KEY/SECRET/PASSPHRASE).
# Whichever file is EMPTY is the lane that stays on the shadow ledger: a folder armed for Bitget
# simply ignores the OKX branch. One armed book per account, always. chmod 600 on every env file.
for _n in sorted(f for f in os.listdir(HERE) if f.endswith(".env")):      # okx/coinbase/bitget…
    ENVF = os.path.join(HERE, _n)
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


def boot_banner():
    """One line in the journal: which key file THIS venue reads, and whether it is armed.

    It names the venue's own file and asks the venue's own keyed flag. An earlier version tested
    OKX_API_KEY/COINBASE_API_KEY only and hard-coded "(both empty)", which printed a calm
    "nothing is sent" on an ARMED Bitget book — the one moment a wrong banner is expensive, because
    it is read as 'not live yet' while orders are going out.
    """
    exe = getattr(rc, "EXEC_MODE", "?")
    keyf = {"okx": "./okx.env", "coinbase": "./coinbase.env + ./coinbase.pem",
            "bitget": "./bitget.env"}.get(exe, "./env files (any *.env here)")
    armed = any(getattr(rc, f, False) for f in ("OKX_KEYED", "BG_KEYED", "CB_KEYED"))
    keyf += " (key PRESENT → orders are real from this cycle)" if armed else " (empty → shadow ledger, nothing is sent)"
    line = (f"crypto_loop: resident on this Mac — cycle every {CYCLE}s · venue per config ({exe}) · "
            f"keys from {keyf} · this is the ONLY armed book for its account "
            f"(the repo mirror ships auto_ack off)")
    rc.journal(line)
    return line


if __name__ == "__main__":
    if "--once" in sys.argv:
        run_once()
        print("crypto_loop: single cycle done (verify mode)", flush=True)
        sys.exit(0)
    boot_banner()
    while True:
        run_once()
        time.sleep(CYCLE)
