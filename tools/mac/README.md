# The Mac crypto book (v4.7.4)

`~/hermes_sentry/crypto/` on the user's Mac runs `crypto_loop.py` under launchd
(`com.hermes.sentry.crypto`, RunAtLoad + KeepAlive, cycle 300 s) — the same engine as this repo
and the MT5 forex build, executing straight against OKX REST. Files to deploy into that folder:
`sentry_core.py run_cycle.py broker_okx.py broker_ledger.py broker_coinbase.py broker_bitget.py
config.json crypto_loop.py` — plus one key file per lane you want armed: `okx.env`, `coinbase.env`, `bitget.env`.
The folder's config differs from the repo's in exactly one line: `auto_ack_on_key: true` (this
is the armed book; the repo mirror is not). Keys: `okx.env` only, chmod 600, never committed.
Alerting is local and session-free (since 2026-11-17, on request): every book mirrors its urgent lines
into `~/hermes_sentry/alerts.outbox`, and the radar (`trade_radar.py`, launchd `com.hermes.radar`, port 8790)
turns that queue into a macOS notification, a Gmail if `~/hermes_sentry/gmail_smtp.json` exists, and a POST
to `$HERMES_ALERT_WEBHOOK` if he wires his own n8n. There is no `[DESK-WAKE]` bridge any more — continuity is
launchd's job, so nothing in this stack depends on an agent session being logged in. Kill switch:
`launchctl bootout gui/$(id -u)/com.hermes.sentry.crypto` for a whole book, or `entries_enabled: false` in
`crypto_desk_mode.json` to keep measuring while refusing new entries — open positions keep their
venue-side TP/SL either way. The folder's config differs from the repo's in one line, `auto_ack_on_key: true`:
this is the armed book, the repo mirror is not, and keys live only in `<venue>.env`, chmod 600, never
committed.

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
* **candles**: `/history-candles` returns closed bars only (no `confirm` flag), so the forming bar is
  dropped by its own open time, and its granularity list is NOT `/candles`'s: `1Hutc`/`4Hutc` are absent
  (the earlier mapping that asked for one got `400171 k-line time range should be [...]`), while the
  day/week/month names exist in BOTH forms and mean different bars — `1D` opens at 16:00 UTC (the
  venue's own UTC+8 day) and `1Dutc` at 00:00 UTC, both measured live. This book asks for `1Dutc`,
  because the OKX book's daily features are cut at 00:00 UTC and two books comparing "yesterday's D1"
  must mean the same candle. Unknown timeframes raise; there is no silent fallback.
* **0.24 R** per trade at a 0.5 % stop (0.02/0.06, read live) against a `live_max_fee_r` cap of 0.25 R:
  it passes, by 0.01 R. Check `fees` on your own account before trusting that.

## Watching it, and pausing it

Every cycle the book writes one small file about itself — `~/hermes_sentry/books/<folder>.json` — and
`monitor.py` (running from `~/hermes_sentry`, kept fresh by `com.hermes.sentry.monitor` every 60 s)
turns those files plus the forex build's own state into **`~/hermes_sentry/TRADING.html`** (and a
`.md` twin for a terminal): per book, the venue it is on, whether it is armed or on the shadow ledger,
what it is waiting on, equity / realized / fees, every open position with **how much R it is carrying
and how far to its stop**, every resting pending with its stop and target, the fee-versus-cap verdict,
and the last lines it cares about.

It is a reader, on purpose. It opens no network, no subprocess, no MT5, and writes only its two files,
so it can neither move money nor break a cycle; if `monitor.py` died, the books keep trading and you
just read `books/*.json` yourself.

```sh
/usr/bin/python3 ~/hermes_sentry/monitor.py --print      # the same page, as text, right now
open ~/hermes_sentry/TRADING.html                        # auto-refreshes every 60 s
```

Pause **new entries** without stopping a book:

```sh
echo '{"entries_enabled": false, "why": "sizing up"}' > ~/hermes_sentry/crypto_desk_mode.json
```

That is the shared switch for all three crypto books (a file of the same name inside one book folder
pauses just that book, and wins over the shared one). It is re-read every cycle, so no restart is
needed either way, and it takes the same shape as the forex build's `desk_mode.json` — one habit per
desk, both plain text.

What a pause does *not* do, and this matters more than what it does: exits, resting stops and TTL
management keep running (a pause that stranded an open position without its protective legs would be
a worse trade than the one it prevented), and the book keeps scanning and journalling every candidate
as `HELD` instead of sending it. So the graded record the sizer scales off keeps growing while paused,
and the run after you flip it back on is better informed, not colder. A switch file that cannot be
parsed also holds entries — fail-safe, never fail-open.

Arm or disarm money with the key file, nothing else: `bitget.env` (or `okx.env` / `coinbase.env` +
`coinbase.pem`), chmod 600, key lines uncommented = armed (`auto_ack_on_key`), re-commented = straight
back to the shadow ledger on the next cycle.

## The research lab (`lab.py`, `com.hermes.sentry.research`) — the part that argues with the playbook

Everything above can *execute* a trade and *grade* it afterwards. None of it could say "that rule is wrong,
and here is the number that says so". A desk that only executes converges on itself: the playbook stays
whatever it was, and the log grows. So `lab.py` is a second loop that never touches the venue and is allowed
to be wrong out loud.

What runs (`~/hermes_sentry/lab.py`, launchd `com.hermes.sentry.research`, every 30 min, `Nice 10`):

- **It replays the real engine, not a copy of it.** `sentry_core.evaluate_symbol` is called bar by bar over
  archived history, with the same `min_score_fire` as the books, and every candidate is resolved against the
  *forward* 15-minute bars and graded through `grade_stats` — the same arithmetic that produced
  `net -22.76R`. If the engine cannot be imported the run is `fatal` and says so; it never reports "no
  trades" for a layout problem.
- **A hypothesis is a filter from a closed list.** `min_score`, `skills`, `cooldown`, `atr_band`, `hours`,
  `max_fee_r`, `no_short`, … Nothing is `eval`'d, and an unrecognised key raises instead of quietly testing
  nothing (that failure mode — a verdict on the old strategy labelled as the new one — is why).
- **The test is paired, not two win rates.** For each idea the trade stream is split kept/dropped and the
  question is the difference in mean R, with a bootstrap CI, compared against a bar that *grows with the
  number of ideas already tried* (`deflated_bar`). An idea that changes no trades is reported `no_op`
  ("that is not a change"), and 400 combinations cannot manufacture a winner past the bar.
- **Three windows, and the last one is the point.** Train tunes, test decides, and a **holdout pinned at the
  first run** is consumed only if the test window already earned it — once per idea, ever. The boundary lives
  in `lab/lock.json`, so the exam date cannot creep as the archive grows; resetting it is
  `--unlock-holdout --i-know` and writes a line into `findings.md`.
- **Flattery is refused in the three places it happens:** a stop entry pays slippage, a bar that touches both
  stop and target is a **loss**, and a trade still open when the data ends is `censored` and excluded, not
  marked at the last close.
- **It reads the live log for ideas.** The worst-performing skill in the graded live book becomes a proposed
  filter with its measured number as the claim — research pointed at this account, not at a textbook.

Output, all read-only for the rest of the desk:

| file | what it is |
|---|---|
| `lab/lab.json` | what `http://<mac>:8790/lab` renders — trials, bar, buckets, verdicts, the pinned holdout |
| `lab/findings.md` | append-only, one block per verdict: claim, filter, paired CI, both windows, trials burned |
| `lab/proposals.json` | the survivors. **Nothing on the execution path reads this file** (§32 proves it) — arming one means editing a book config by hand |
| `lab/data/*.json` | the bar archive. Grows every run, which is why its power increases while it waits |

`LAB_RUN_SEC` (default 600, set to 600 in the plist) bounds fetching so a run always writes a report; a
partial window is recorded in the page as such, never as a quiet market. `LAB_ENGINE` pins which book's copy
of the engine to replay — currently `crypto-bitget`, because a rule proven on OKX's fees is not a rule proven
on the fee schedule this account would actually pay. `run_cycle` comes from wherever the import finds it, and
`sources` + `cost_source.fees` in `lab.json` say which files those were, so a verdict can be re-checked
against a different venue's costs instead of trusted.
