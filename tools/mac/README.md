# The Mac crypto book (v4.7.4)

`~/hermes_sentry/crypto/` on the user's Mac runs `crypto_loop.py` under launchd
(`com.hermes.sentry.crypto`, RunAtLoad + KeepAlive, cycle 300 s) — the same engine as this repo
and the MT5 forex build, executing straight against OKX REST. Files to deploy into that folder:
`sentry_core.py run_cycle.py broker_okx.py broker_ledger.py broker_coinbase.py broker_bitget.py
config.json crypto_loop.py` — plus one key file per lane you want armed: `okx.env`, `coinbase.env`, `bitget.env`.
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

## The Bitget lane (v4.7.4) — the venue that already exists

`bitget.env` is the third key file; `crypto_loop.py` loads every `*.env` in this folder, so a book can
hold any lane's credentials and the empty ones do nothing. Bitget is the lane worth arming first if you
already have a verified account there, for one reason: it is the only venue of yours whose API answers
from BOTH ends (Binance returns HTTP 451 and Bybit CloudFront-403 to this sandbox), so its payloads were
built and measured against the live venue instead of typed from a doc page.
`python3 broker_bitget.py fees` prints the schedule it read, per symbol, and whether the current
`live_max_fee_r` still passes.

A Bitget book is a copy of the folder, same as the Coinbase one, with three config lines:

```sh
cp -R ~/hermes_sentry/crypto ~/hermes_sentry/crypto-bitget
cd ~/hermes_sentry/crypto-bitget && rm -f state.json journal.md ledger.json STATUS.md
```

```python
import json, collections
c = json.load(open("config.json"), object_pairs_hook=collections.OrderedDict)
c["execution"] = "bitget"; c["fees"] = {"maker": 0.0002, "taker": 0.0006}
c["stop_floor_frac"] = 0.0; c["auto_ack_on_key"] = True
json.dump(c, open("config.json", "w"), indent=2)
```

```sh
BITGET_DRY=1 BITGET_DRY_EQUITY=20000 /usr/bin/python3 run_cycle.py   # rehearsal: real payloads, no orders
python3 broker_bitget.py fees                                        # the venue's own fee table
```

Then point `com.hermes.sentry.crypto.bitget.plist` (shipped in this folder) at `crypto-bitget` and
`launchctl bootstrap gui/$(id -u) <that plist>`. The book is worth running resident even with no key:
it scans Bitget's candles, sizes itself off its own grades and books shadow fills with Bitget's fees, so
the day the key lands, the only thing that changes is whether the order leaves the machine.

Differences that matter, because Bitget is not OKX with different letters:
* **size is in coins** — no `ctVal` contract multiplier. Reusing OKX's contract maths changes your size.
* **a trigger is a field, not an endpoint** — `orderType=limit` + `triggerType=fill_price` +
  `triggerPrice` (+ `executePrice` collar) on `/api/v2/mix/order/place-order`.
* **candles**: `/history-candles` takes `1H/4H/1D` and REFUSES the `*utc` spellings `/candles` accepts,
  and it returns closed bars only (no `confirm` flag), so the forming bar is dropped by its own open
  time. Daily bars land at 16:00 UTC — the venue's day. A book that mixes feeds would grade on a
  different day than it trades.
* **0.24 R** per trade at a 0.5 % stop (0.02/0.06, read live) against a `live_max_fee_r` cap of 0.25 R:
  it passes, by 0.01 R. Check `fees` on your own account before trusting that.
