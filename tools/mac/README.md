# The Mac crypto book (v4.7.3)

`~/hermes_sentry/crypto/` on the user's Mac runs `crypto_loop.py` under launchd
(`com.hermes.sentry.crypto`, RunAtLoad + KeepAlive, cycle 300 s) — the same engine as this repo
and the MT5 forex build, executing straight against OKX REST. Files to deploy into that folder:
`sentry_core.py run_cycle.py broker_okx.py broker_ledger.py broker_coinbase.py config.json crypto_loop.py okx.env` (plus `coinbase.env` for the Coinbase lane).
The folder's config differs from the repo's in exactly one line: `auto_ack_on_key: true` (this
is the armed book; the repo mirror is not). Keys: `okx.env` only, chmod 600, never committed.
Desk alerts reuse the forex build's wiring: `alerts.outbox` + `[DESK-WAKE]` POST to the jarvis
bridge on 127.0.0.1:8768. Kill switch: `launchctl bootout gui/$(id -u)/com.hermes.sentry.crypto`
— open positions keep their venue-side TP/SL.

## The Coinbase lane (v4.7.3) — same folder, different keys file

`coinbase.env` in this folder is the Coinbase counterpart of `okx.env`: `crypto_loop.py` loads both,
so one deployed folder can hold either lane's credentials and the one that is empty does nothing.
A second, independent Coinbase book (its own state, its own ledger, its own journal) is a copy of
the folder:

```sh
cp -R ~/hermes_sentry/crypto ~/hermes_sentry/crypto-coinbase
cd ~/hermes_sentry/crypto-coinbase && rm -f state.json journal.md ledger.json trades_log.jsonl
python3 - <<'PY'
import json, collections
c = json.load(open("config.json"), object_pairs_hook=collections.OrderedDict)
c["execution"] = "coinbase"; c["fees"] = {"maker": 0.0025, "taker": 0.0040}
c["stop_floor_frac"] = 0.02; c["auto_ack_on_key"] = True
json.dump(c, open("config.json", "w"), indent=2)
PY
COINBASE_DRY=1 COINBASE_DRY_EQUITY=20000 /usr/bin/python3 run_cycle.py   # rehearsal: real payloads, no orders
```

Read the rehearsal for the lines starting `WIDENED` and the `fees ~$... (0.40R)` tails: that is the
venue's cost being paid for with a wider stop instead of with a bigger bet. Two rules, because this
folder can hold real money:

1. Never arm two books on one account. If the OKX key lives in `crypto/okx.env`, do not copy it into
   `crypto-coinbase/okx.env` — and if you move it, delete it from the folder you stopped trading.
   Two armed books double-send; one blank env file is the disarm switch, no boot-out needed.
2. A Coinbase book without `stop_floor_frac` set is a book that only journals refusals: at 0.5 %
   stops the venue takes 1.6-2.4 R, so `live_max_fee_r` (0.25 R) says no to every signal. That guard
   is the difference between an expensive bot and a losing one.

Rehearsal-only switches, all honoured by both lanes: `COINBASE_DRY=1` (build and journal the exact
payload, send nothing), `COINBASE_DRY_EQUITY` (pretend wallet size), `COINBASE_TEST=1` (Exchange
sandbox host, and `run_cycle` stamps LIVE off). Shorts: Coinbase Exchange is spot for this book, so a
short signal is graded on paper and the ledger keeps its side of the tally — the strategy loses its
downside half there, which is a real reason to keep OKX as the default and not a preference.
