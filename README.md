# Sentry v4.7.0 — GitHub-native trading brain (no MT5, no Mac, no Wine)

The same checklist engine from the Mac build (`sentry_mac.py` v3.1) — and since v4.7.0 that is
literally true, not a slogan: the full detector array (22 §12 candle patterns, 16 skill families,
five timeframes M5/M15/H1/H4/D1, same thresholds and geometry) now runs for the crypto book on
**GitHub Actions**, fed by OKX public candles. One workflow run = one full scan cycle, every
10 minutes, 24/7 (crypto has no weekend gap — MT5 demo servers do).

## Engine parity — what is the same as the Mac, and what is deliberately not

| | Mac/MT5 build | This build (v4.7.0) |
|---|---|---|
| candle patterns (§12) | 22 | **same 22, ported verbatim** (`C-H1-*` / `C-M15-*` carry the Mac's names) |
| skill families | S1,S2,S3,S4,S10,S11,S13,S15,S16,S18×2,S21,S22,S23,S24,S25 | **all of them, same order, same entry/SL/TP formulas, same score bumps** |
| timeframes | M5 M15 H1 H4 D1 | **the same five** (RSI2 on 5m closes, Donchian/ichimoku/squeeze on H1, HTF bias and pivots from D1, H4 gate) |
| data source | MT5 terminal | OKX public klines — the same venue the orders go to; thin or stale data **fails the cycle red**, never a quiet "scan ok" |
| session gates | red-window ban + T11 equity windows | Mac already exempts crypto from both; on a crypto-only universe they are no-ops (S25's liquidity-hour read is kept, like the Mac keeps it for crypto) |
| caps | theme/day caps advisory ("FULL FREEDOM") | **hard**: one pending per symbol, `max_open`, `pending_ttl_h`, fee ≤ `live_max_fee_r`, notional ≤ 25 % equity, `live_ack` |
| chandelier trail | after +1.5R, 2×ATR both directions | **now both directions** (v4.7.0 fixed the long-only trail) |

**Start here → [`STATUS.md`](STATUS.md)** — rewritten by the bot at the end of every cycle: what
venue it is on, what is resting on the book, what it holds and at what P/L, and the last 12 signals
with what happened to each one. `journal.md` is the full decision log; `STATUS.md` is the page.

```
┌─ Actions cron (*/10) ─┐   ┌─ this repo = the database ────────────┐
│ run_cycle.py          │──▶│ state.json        (orders/positions)  │
│  1. fetch klines      │   │ ledger.json       (simulated fills)   │
│  2. reconcile fills   │   │ journal.md        (every decision)    │
│  3. evaluate skills   │   │ trades_log.jsonl  (accuracy → sizing) │
│  4. size + fire       │──▶ venue: OKX perps / Coinbase / Alpaca    │
│  5. push_memory (API) │   └───────────────────────────────────────┘
└───────────────────────┘
```

- `sentry_core.py` — pure brain: EMA/RSI/ATR/Bollinger/pivots, the full 22-pattern §12 candle
  engine, **all 16 skill families** (S1/S2/S3/S4/S10/S11/S13/S15/S16/S18×2/S21/S22/S23/S24/S25
  + `C-*` candle library on H1 and M15), 5-point scoring, accuracy-based self-sizing ($50–$200).
- `broker_ledger.py` — default venue: Coinbase *public* candles + simulated fills in `ledger.json`.
  Zero accounts, zero secrets, nothing to rot.
- `broker.py` — optional Alpaca paper REST client (stdlib only, no pip installs).
- `run_cycle.py` — orchestrator + state machine + **loud-death guards** (exits red on stale or
  thin data, never "scan ok" on nothing) + `push_memory()` (writes memory through the Contents
  API with retry, so two runners can never conflict the way `git push` did).

## Execution modes (one config line)
- **`"execution": "okx"` (what ships):** OKX via `broker_okx.py` — real orders on perps, **0.02 %/0.05 %
  fees**, TP/SL attached to the entry order by the venue, and the short side of the checklist actually
  tradable. `vars.OKX_SIM=1` switches to OKX's simulated-trading engine: same host, same signatures,
  real matching, **no money** — the rehearsal Coinbase cannot offer. Same no-key fallback to the
  shadow book (on the same OKX public candles the scanner reads, so prices are unchanged; only the
  fee schedule moved).
- **`"execution": "bitget"` (v4.7.4 — the lane for an account that already exists):** Bitget USDT-M
  perps via `broker_bitget.py` — 0.02 %/0.06 % **read from the venue's own `/market/contracts`**, which
  prices this book's 0.5 % stop at 0.24 R and therefore **inside** `live_max_fee_r` (OKX 0.20 R, Coinbase
  base tier 2.39 R). Shorts are real (`CAN_SHORT`), both protective legs attach to the entry order, and
  the size is in COINS — Bitget has no contract multiplier, so the OKX maths must not be reused. Sizes
  floor to `volumePlace`, prices to `pricePlace`, and a sub-`minTradeUSDT` order is refused locally.
  The data plane follows the venue: a Bitget book scans Bitget's own closed history-candles (spacings
  proven 300/900/3600/14400/86400 s, forming bar dropped by its open time — that endpoint has no
  `confirm` flag), because judging a trigger on another exchange's last price is how a live order
  fills at a price the paper book never saw. `BITGET_MARGIN=isolated|crossed`, `BITGET_HEDGE=1` for a
  hedge-mode account (unproven without a key, so the assumption is journalled), `BITGET_DRY=1` for a
  payload rehearsal, `OKX_DATA=1` to scan OKX candles while trading Bitget.
- **`"execution": "coinbase"`:** Coinbase via `broker_coinbase.py` — **real orders on
  a real book**, on either Coinbase API (retail Advanced Trade or institutional Exchange; the
  presence of a passphrase picks which, see "Going live"). The key lives only in Actions Secrets.
  With no key in the runner it runs the shadow ledger on the same public data and stamps
  `venue shadow-ledger(coinbase-no-key)` into the journal line, so "did that touch real money?" is
  always answerable from the log.
- **`"execution": "ledger"`:** shadow book only — real prices, simulated fills in `ledger.json`.
  Paper fills are honest about price (never worse than the tape) but have no depth model.
- **`"execution": "alpaca"`:** Alpaca paper venue (resting orders on their engine). Needs
  `ALPACA_KEY_ID` + `ALPACA_SECRET`. Same brain, different venue.

## Going live on OKX (the Mac book trades; this repo is the mirror)

v4.7.2 moved the armed book to the Mac (`~/hermes_sentry/crypto/`, source in `tools/mac/`). The keys
live in that folder's `okx.env` and nowhere else. This repo keeps scanning, grading and rehearsing on
the shadow ledger — its config ships `auto_ack_on_key: false` precisely so two runners can never
fire the same order. Arming the Mac book is two actions, no GitHub involvement:

1. Mint the API key with **Trade only**. No withdrawal, no transfer. Turn on the withdrawal whitelist
   on the account side.
2. Paste the three values into `~/hermes_sentry/crypto/okx.env` on the Mac (uncomment the three lines),
   then `launchctl kickstart -k gui/$(id -u)/com.hermes.sentry.crypto`. The journal prints
   `LIVE ACK — granted by key presence`; from the next cycle the orders are real.

To rehearse on fake money first (purely optional): `OKX_SIM=1 python3 broker_okx.py rehearse` from
the same folder — simulated-trading header, real payload shapes, re-find by `clOrdId`, amend, cancel.
`OKX_DRY=1 OKX_DRY_EQUITY=20000 python3 run_cycle.py` prints venue-shaped `ORDER SENT` bodies against
the real book without sending. STATUS.md in this repo reflects the mirror; the Mac's own
`crypto/journal.md` + hermes desk alerts are the live record.

## Bitget, Binance, Bybit: which of YOUR accounts becomes the executor (v4.7.4)

The three venues you already hold were probed from both ends, not from a blog:

| venue | from the GitHub runner (US egress) | from your Mac (MY residential) | what that decides |
|---|---|---|---|
| Bitget | **200** on market data, `40006 Invalid ACCESS_KEY` on private (path live, key absent) | **200** | built and measured here: the only lane whose payload can be checked before money moves |
| Binance | `451` — *"Service unavailable from a restricted location"* | **200** | an adapter written here could never be executed once; it needs the Mac as its test rig first |
| Bybit | CloudFront `403` for this country | **200** | same |
| OKX | 200 | 200 | what has been running since 4.7.x |

So Bitget is the lane that went in: `execution: "bitget"` on the same engine, the same guards, its own
book folder, keys in `bitget.env`. On your Mac the fee schedule was re-read from the venue and every one
of the ten symbols publishes 0.02 %/0.06 % with `symbolStatus=normal`, min 5 USDT notional, size steps
from `volumePlace` — `python3 broker_bitget.py fees` prints that table again, live, and tells you whether
the current `live_max_fee_r` still passes. The margin is genuinely thin (0.24 R against a 0.25 R cap),
which is stated in `config.venue_notes` rather than hidden: if your account's tier turns out worse, the
honest fix is `stop_floor_frac: 0.006`, not a bigger cap.

Bybit and Binance are deliberately NOT shipped as adapters. Writing two more money paths from a
sandbox that both venues refuse to talk to would produce code that has never executed a single
line — exactly the "toy" failure this project has already been called out for. The probe above is the
seed: run it on your Mac, and the moment you want one, the same 400 lines of `broker_bitget.py` get
translated against a host that answers.

## Going live on Coinbase (the lane he asked about — built, rehearsed, not the default)

`execution: "coinbase"` is not a stub and I am not guessing about it: on 2026-11-14 the full cycle was
run against it with real market data, six signals turned into six real-shaped orders, and the numbers
came back. What that rehearsal says, in the venue's own words:

| Coinbase Exchange tier (30-day volume) | maker/taker | fee per trade at this book's 0.5 % stop | verdict |
|---|---|---|---|
| $0–10 k | 0.40 / 0.60 % | **2.39 R** | every live signal refused by `live_max_fee_r` — correct, not a bug |
| $10–50 k | 0.25 / 0.40 % | 1.60 R | refused |
| $50–100 k | 0.15 / 0.25 % | 1.00 R | refused |
| $100 k–1 M | 0.10 / 0.20 % | 0.80 R | refused |

The lane is only tradeable here two ways, and v4.7.3 ships the second one as a config line:
**`stop_floor_frac: 0.02`** — the stop is widened to what the fee can live inside, the target is scaled
by the same factor so R stays R, size falls out of the wider distance, and the same six signals went out
at **0.40 R** instead of 0.74–0.86 R with risk per trade untouched at $75.00. Journal lines say
`WIDENED —` for every one of them; nothing about the re-price is quiet. What it costs is honesty about
the history: the widened book is a different trade, so do not read the OKX grade history as its track
record. That is why the floor ships at `0.0` and the OKX book is byte-for-byte unchanged.

Three things a fee table will not tell you, from the same investigation:
1. **The retail app and the API are different accounts.** The Exchange API (`api.exchange.coinbase.com`,
   the one whose fee ladder is above) is a separate signup with a **passphrase** on the key; the retail
   Advanced Trade key signs a different host with a CDP ES256 private key. `broker_coinbase.py` speaks
   both — a passphrase in `coinbase.env` selects `exchange`, otherwise `advanced`; `COINBASE_MODE` overrides.
   A retail key pointed at the Exchange host returns 401 and the adapter says so instead of retrying.
2. **Malaysia.** The retail app's funding rails (MYR, local card) are not the plan — there is nothing to
   route money through. The Exchange API is a keys-and-crypto affair: fund it by on-chain USDC/BTC
   transfer from wherever the money already sits, and eligibility is decided by KYC, not by my guess.
   OKX needs the same on-chain transfer and is already wired, which is the whole reason it ships.
3. **Coinbase Exchange is spot for this book.** `CAN_SHORT` is absent, so a short signal is graded on
   paper (`paper-graded (spot can't short)`) rather than sold into the book — 12 of the 18 signals in
   that rehearsal were shorts. OKX perps trade both sides and attach TP/SL venue-side; that is a strategy
   difference, not a preference.

Arming it, when you want it: the same file shape as `okx.env`, in the Coinbase folder
(`tools/mac/coinbase.env` → `~/hermes_sentry/crypto-coinbase/coinbase.env`) — `COINBASE_API_KEY` plus
`COINBASE_CDP_PEM` (retail) or `COINBASE_API_SECRET` + `COINBASE_API_PASSPHRASE` (Exchange). Keys present
+ `auto_ack_on_key: true` is the acknowledgement; the clamps (`live_max_risk`, `live_max_risk_frac`,
`max_notional_frac`, `live_max_fee_r`) are unchanged and still bind every order. Read the account's true
tier with `GET /fee` before you set `config.fees` — the guard prices every trade off it.

**What moved in 4.7.3:** the Coinbase lane measured end-to-end and `config.stop_floor_frac` added (fee-aware stop widening, default 0 = no behaviour change). **What moved in 4.7.2:** execution home is the Mac; repo config arms on nothing (`auto_ack_on_key`
false — the gate itself stays tested, and the Mac copy ships it true). The runner sources
(`tools/mac/`) now live in this repo too, so both books are one source of truth.

`OKX_INSTTYPE` picks `swap` (default — perps, TP/SL on-venue, shorts) or `spot` (no leverage; an opening
short is refused outright, and the shadow ledger stays spot-only either way, so paper and live grade the
same). `python3 broker_okx.py verify` is the read-only account check CI runs on every push when a key exists.

**What moved in 4.7.0 (engine parity):** `sentry_core.py` was replaced by a line-for-line port of the
Mac build's scan block — 22 candle patterns instead of 13, 16 skill families instead of 6, five
timeframes (M5/M15/H1/H4/D1) instead of three. The data plane is now OKX public candles regardless of
execution venue (the same feed live orders trade against), the chandelier trail runs on shorts, and
stale/`quotes []` scans fail the cycle red instead of journalling "scan ok". Nothing else changed:
sizing, grading, fees, TTL and every money-guard are the 4.6.0 code paths, unedited.
Grades before this release were earned on the smaller sensor set; the sizer keeps its blended 0.5
prior for skills with no history, so new families (`S3`, `S21`–`S25`, the nine added candle names)
start at floor size and scale up only on results they have actually posted.

**What moved in 4.6.0:** `execution` and `fees` in `config.json` became OKX's. Grades before this commit
were netted at Coinbase's 0.40/0.60 % and the ledger's `fees_paid` still reflects those; from here the
book is priced the way the venue it will trade on charges, which is the point — a paper score earned
against the wrong fee schedule is not a score.

## Going live on Coinbase (alternative venue)

There are **two** Coinbase APIs and one Coinbase bot. `broker_coinbase.py` speaks both; which one
it uses is decided by the credentials you paste, not by a code change:

| you have | set | host | what changes |
|---|---|---|---|
| a key from your **Coinbase account** (Settings → API keys → *Advanced Trade* / CDP) | `COINBASE_API_KEY` + `COINBASE_CDP_PEM` (or `COINBASE_API_SECRET` on a legacy key) | `api.coinbase.com/api/v3/brokerage` | JWT auth, terms nested in `order_configuration`, sizes as strings, `trigger`/`stop_direction` on the order itself |
| a key from **exchange.coinbase.com → API** (institutional, separate signup, separate balance) | `COINBASE_API_KEY` + `COINBASE_API_SECRET` + `COINBASE_API_PASSPHRASE` | `api.exchange.coinbase.com` | HMAC headers, flat payload, `client_oid` must be a UUIDv4 |

A passphrase in the environment selects `exchange`; anything else selects `advanced`. Override with
`COINBASE_MODE` (an Actions *variable*, which the workflow already passes through, so switching
venues never needs a commit). **A retail key cannot sign at the Exchange host** — that is a hard 401,
so `run_cycle.py` fails at boot with that sentence instead of sending 80 orders into a wall.

1. Mint the key with **View + Trade only** (never transfers/withdrawals). For retail, choose
   *"Coinbase API Key"* (CDP, `organizations/…/apiKeys/…`) and paste the generated **private key**
   into `COINBASE_CDP_PEM` — the retail API authenticates with a signed JWT, so the key pair alone
   is not enough on current accounts.
2. Actions → Secrets and variables → Actions → `COINBASE_API_KEY`, then `COINBASE_CDP_PEM` *or*
   `COINBASE_API_SECRET` (+ `COINBASE_API_PASSPHRASE` for an Exchange key).
3. `config.json`: `"execution": "coinbase"` **and `"live_ack": true`** — plus change `fees` to
   `{"maker": 0.004, "taker": 0.006}`, because grading charges those numbers. Expect the live guard to
   then REFUSE entries at `live_max_fee_r: 0.25`: at Coinbase's base tier a 0.55 % stop pays 1.82R in
   fees, more than the trade risks. That is not a bug to route around — it is why `execution` ships as
   `okx`. Set `live_max_fee_r: 0` only if you decide fees are not your problem.
4. Fund it (see **The wallet** below for the size that makes the signals actually fire). Then read
   `journal.md`.
5. The one thing still unproven end-to-end: **the cid ⇄ order-id round trip against a live venue**.
   `test_data.py` pins both directions offline (map out, read back, normalize) and the DRY run shows
   the exact bytes, but no order has ever been placed and re-found on a real account — no key has
   been connected to do it with. The first funded cycle must therefore be watched: `ORDER SENT`
   followed on the next cycle by `FILL — …` for the same symbol means the round trip worked. If the
   journal says `ORDER SENT` and then `EXPIRED` with no fill, the order is on the venue and Sentry
   cannot see it: stop, cancel by hand, tell the journal (`journal.md` is append-only — a wrong line
   there is data, not noise).

Until a key is present the bot scans, sizes, journals `GATE — …` and sends nothing. The live gates
(`live_gate()` in `run_cycle.py`) each trace to a real defect found on this account, not ceremony:

| gate | why it exists |
|---|---|
| `live_ack: true` **or** a trade-only key present where `auto_ack_on_key: true` (the Mac book ships it true; this repo ships it **false** — v4.7.2, mirror never fires) | a leaked secret must not be enough to trade — and key-minting is human-only anyway, so key presence is accepted as the acknowledgement on the armed book; clamps below bound what a planted key could do |
| `min_grade_before_live` = 0 (was 8) | you ruled out the paper-first wait; the sizer cold-starts at its floor ($50) and the live clamps cap it at $25 / 1 % equity, so the first live trade is small by construction, not by borrowed confidence |
| heartbeat younger than `max_gap_h` = 2 h | nothing watches the book between runs (see the cadence section) — a 10 h gap is not a 10-minute bot |
| live risk = min(sizer, `live_max_risk` $25, `live_max_risk_frac` 1 % of equity) | sizing live by feel is how a bot loses money fast; the sizer earns its size, these two bound it |
| notional ≤ `max_notional_frac` × equity, or **SKIP** | the 2026-11-14 mis-mapped candles produced a $261k order for "$100 of risk". Size is never quietly trimmed to fit — a $2 "risk" is spread and fees, so the trade is refused and the journal says what account it wanted |

Two Exchange-API traps the adapter handles, both pinned by `test_data.py`:
- **`client_oid` must be a lowercase UUIDv4.** Coinbase *accepts* a malformed one, then never
  processes it and never returns it from any later REST call — a silently vanished order. Sentry's
  ids look like `sentryXRPUSD1794662610992n5`, so `oid_for()` maps each cid to a deterministic
  UUIDv4 (and back) and never sends the raw cid.
- **A stop order executes as a LIMIT once triggered.** The limit must clear the trigger in the
  direction of travel, or the order triggers and sits unfilled forever; on coarse-tick products a
  naive 0.15 % slack rounds *back onto* the trigger, so it widens to at least one full tick
  (Decimal, because `int(0.94 / 0.01)` is 93).

No-money rehearsals: `COINBASE_DRY=1` builds and prints the exact payload it would send (and
`COINBASE_DRY_EQUITY` rehearses any wallet size through the real sizing path); `COINBASE_TEST=1`
points at Coinbase's Exchange sandbox host (which also disarms the live gates);
`python3 broker_coinbase.py` runs a read-only auth/wallet check and places nothing.

## Which venue? Measured from the runner, not from a comparison site

The bot runs on GitHub Actions runners, which are **US-based**, so a venue's geo-blocks decide whether
it is usable at all — fee tables on a review site do not. Probed directly from the same egress on
2026-11-14 (public endpoint + one unauthenticated private call, so "auth error" means *reachable,
needs a key*):

| venue | from a US IP | base-tier round trip at a 0.55 % stop | shorts | venue built here? |
|---|---|---|---|---|
| **OKX** | ✓ market 200 / private 401 (needs key) | **0.07R** | yes (perps) | yes — `execution: "okx"` |
| Coinbase (retail or Exchange) | ✓ | 1.82R — the fee guard refuses it | no (spot) | yes — `execution: "coinbase"` |
| Kraken | ✓ | ~0.76R | no | no |
| Bitget, MEXC, Gate, KuCoin | ✓ | 0.09R–0.5R | yes (perps) | no |
| **Binance** | ✗ refused: *"Service unavailable from a restricted location according to 'b. Eligibility'"* | (would be 0.36R) | — | no |
| **Bybit** | ✗ CloudFront geo-block, public data included | (would be 0.13R) | — | no |

So the two venues I would otherwise have recommended on fee grounds alone (Binance, Bybit) are
**untradeable from this runner** — worth knowing before anyone spends a week on them. OKX is the lane
where the arithmetic works *and* the plumbing is reachable: `0.07R` against a `0.25R` cap, shorts
live, and `OKX_SIM=1` proves the whole order lifecycle before a dollar exists. Three secrets to get
that: `OKX_API_KEY`, `OKX_API_SECRET`, `OKX_API_PASSPHRASE` (OKX signs with all three; a missing one
fails at boot instead of silently degrading to paper).

Rehearse without money, in this order:
```bash
python3 broker_okx.py                # read-only: wallet, instrument ticks, candle mapping, id rules
python3 broker_okx.py rehearse       # OKX_SIM=1: place a conditional 20 % away from the tape, find it
                                     # by clOrdId, cancel it. Proves the round trip with fake money.
```

## The wallet: how big, and what the venue takes

The account has to satisfy two independent floors. Both are measured through the shipped code, not
estimated — this was rehearsed by running a live cycle against `COINBASE_DRY_EQUITY` at six sizes:

| wallet | orders actually built | refused for size |
|---|---|---|
| $1,000 | 0 | 7 |
| $2,500 | 0 | 7 |
| $5,000 | 0 | 7 |
| $10,000 | 2 | 5 |
| $20,000 | 6 | 0 |
| $50,000 | 6 | 0 |

Malaysia-specific, because it changes the funding path: Coinbase's own identity-verification page
does list Malaysia as a signup country (MyKad/passport/licence, no proof-of-address), but Coinbase's
**cash balance is US/EMEA only**, so there is no MYR bank rail in or out. In practice money arrives
as crypto — USDC on a network Coinbase supports, sent from a locally licensed DAX (Luno/HATA take
MYR by FPX or Touch 'n Go). Pick the network deliberately and match it exactly on both sides:
Coinbase states plainly that funds sent over the wrong network cannot be recovered.

**Under ~$10k this playbook will not trade at all; ~$20k is the floor for it to fire at full rate.**
That is arithmetic, not conservatism: risking $75–$200 through a 0.4–1.2 % stop *requires* $10k–$40k
of notional per position, and `max_notional_frac` refuses to shrink the risk instead of the stop.
$50k buys headroom and, on any venue, moves you up a fee tier.

**Fee cost is a property of the strategy, so it is now priced in.** `config.json` carries
`"fees": {"maker": 0.004, "taker": 0.006}` and every simulated *and* live-leg fill pays it: cash,
realized P&L and the R that grading uses are all net. The number that matters is the round trip
expressed in R — `(maker + taker) / stop_width` — because a 1R trade that pays 1.8R in fees is not a
trade:

| venue (base tier) | 0.40 % stop | 0.55 % | 0.67 % | 0.80 % | 1.20 % |
|---|---|---|---|---|---|
| Coinbase Advanced Trade retail 0.40/0.60 | 2.50R | 1.82R | 1.49R | 1.25R | 0.83R |
| Kraken 0.16/0.26 | 1.05R | 0.76R | 0.63R | 0.52R | 0.35R |
| Binance 0.10/0.10 | 0.50R | 0.36R | 0.30R | 0.25R | 0.17R |
| Bitget perps ~0.02/0.05 | 0.17R | 0.13R | 0.10R | 0.09R | 0.06R |

So on Coinbase's retail schedule at this strategy's own stop widths, **the venue takes more per round
trip than the stop risks**, before any view on direction. Two honest responses, both of which are the
user's decision and not the bot's:
- **make the venue pay less**: a cheaper/maker-only venue (fees ≤ 0.25R at these stops), or
- **trade less often at more edge**: which is what the score floor and `pending_ttl_h` already do —
  *not* wider stops. Widening the stops to make the fees fit would change the risk the whole score
  history was earned on, so the bot refuses to do it silently.

`"live_max_fee_r": 0.25` turns that into a guard: a **live** order whose round-trip fee costs more
than 0.25R of its own risk is refused with the dollars in the journal (`SKIP — venue fees cost
1.72R (cap 0.25R) on a 0.70 % stop — $42.94 paid to trade for $25.00 of risk`), and if that refusal
empties the cycle you get one `ALERT` line saying so. Set it to `0` to trade anyway. The shadow book
is charged the same schedule, so its accuracy number — the number the sizer scales — is the venue's
number, not a fee-free fantasy. Verified the day it shipped: a paper AVAX trade that closed at
**+0.61R on the chart graded −0.61R net of 1.22R in fees**, and became a loss in the score history.

## Files you care about
- **`STATUS.md`** — the page you look at: orders resting, positions, last signals, accuracy, sizing.
  Machine-written every cycle, safe to bookmark, never edited by hand.
- **`journal.md`** — every cycle and every decision, newest at the bottom. This is the bot's diary;
  read it instead of logs (Actions keeps 90 days, git keeps forever).
- **`trades_log.jsonl`** — one row per signal (symbol, skill, entry/stop/target, score, size) and
  the grade written back into that same row when it closes. Its rolling win rate is what the bot
  sizes itself with, so this file is pushed whole each cycle rather than appended.
- **`state.json`** — machine state: open orders, positions, `sizing` tiers, `seen` (one fire per
  symbol-skill-day), `realized`.
- **`ledger.json`** — cash, positions and marks in ledger mode.
- **`.github/workflows/scan.yml`** — the cron + `permissions: contents: write` that lets it commit memory.

## Run it yourself (3 commands, from a machine with python3)
```bash
git clone https://github.com/akramsakib/sentry.git && cd sentry
python3 test_data.py         # offline checks (row order, guards) — must print "0 checks failed"
python3 run_cycle.py         # one full cycle, no accounts, no keys — prints the decisions
```
To run it as a service on GitHub: push these files to a repo, then
Actions → *sentry-cycle* → **Run workflow**. Green check + a `scan ok · 10 symbols · …`
line landing in `journal.md` = working. A **red** run is the alarm; GitHub emails you.

To make the repo **private** (recommended once you add real keys): GitHub → fine-grained PAT with
`Contents: Read & write` scoped to this repo, then `git remote set-url origin
https://<TOKEN>@github.com/<you>/<repo>.git && git push`. Free-tier private repos get 2,000
Actions minutes/month; this bot burns ~1–2 min per cycle (~5,000/yr at 10-min cadence), so a
private repo at 10-min cadence needs either a paid plan or a slower `cron` (e.g. `*/30`).

## Data integrity: the Coinbase candle bug (2026-11-14), kept here so it cannot come back quietly
Coinbase's `/candles` rows are `[time, low, high, open, close, volume]`. An earlier version of
`broker_ledger.py` read them as OHLC, which made every bar "bullish" (close=high > open=low) and
turned `high-low` into the *body*. Result: `C-*-three-soldiers` fired on five symbols at once with
stops 0.04% wide, and `risk / stop-distance` then asked for 3 454 SOL — $261k notional to risk $100.
`test_data.py` pins the row order, the forming-candle pop, an impossible-bar rejection, and both
sizing guards; the workflow runs it before every cycle, so a regression is a red run, not a bad trade.

## Cadence: GitHub's cron is throttled on this account (read this)
Measured on 2026-11-14: `sentry-cycle` declares `*/10 * * * *` and every *other* trigger
(`push`, `workflow_dispatch`, `repository_dispatch`) fires in seconds, but **zero** scheduled
runs appeared for ~4 h. It is not this repo: a sibling repo of the same account
(`Trading-Bot`, cron `3,18,33,48 * * * *` = 96 runs/day) delivered **4** runs in the last 24 h
with 4–8 h gaps, and its 1 358 historical schedule runs prove the mechanism works there.
GitHub is queue-throttling (or silently muting) high-frequency crons for this account — a
community-reported behaviour (GitHub community discussions #208110, #209473, #209838, Sep–Nov 2026).

Three ways to get a real clock, best first:

1. **External pinger → `repository_dispatch` (recommended, free).** Any 10-min cron that POSTs:
   ```bash
   curl -sS -X POST \
     -H "Authorization: Bearer $GH_PAT" -H "Accept: application/vnd.github+json" \
     https://api.github.com/repos/OWNER/REPO/dispatches \
     -d '{"event_type":"sentry-tick"}'
   ```
   `GH_PAT` = a fine-grained token scoped to this repo with **Actions: Read and write** only.
   A Cloudflare Worker + Cron Trigger is 15 lines and free; a plain `crontab` on any always-on
   box (including the Mac) works too. Verified from a cold shell on 2026-11-14: `204` → run
   created in ~3 s, full cycle, memory committed (that is how run #8 happened).
2. **Let the watchdog push it along.** `sentry-watchdog` (hourly) exits red when the journal is
   stale **and dispatches a fresh cycle itself** — `workflow_dispatch` is one of the two events a
   `GITHUB_TOKEN` may fire, so no PAT is needed for that path. You get at least a few cycles/day
   even if GitHub never honours the 10-min cron.
3. **Accept it.** Crypto has no session gap, so a cycle every 4–8 h is still a usable swing bot;
     Because that is the mode now running, `config.json` also carries **`pending_ttl_h: 6.0`**:
     a resting entry trigger older than that is expired (`EXPIRED — … setup no longer valid`)
     rather than left live to fill on a chart that moved on hours earlier with nobody watching.
   the state machine reconciles whatever happened while it slept. Do not call it an M15 bot then.

Do **not** "fix" this by ending each run with a delayed self-dispatch: the sleep needed to space
runs would keep a runner occupied 24/7, which is exactly what GitHub's abuse detection disables.

## The win rate (and why only one file is allowed to compute it)

Asked for his win rate on the radar, the fast answer would have been a `toFixed(1)` in the page's JS. That is
how two dashboards start disagreeing — and here a third number matters more than either: the **weighted**
accuracy the sizer multiplies risk by. So the maths lives in `tools/mac/grade_stats.py` and everything else
calls it:

| surface | what it does with the record |
|---|---|
| `book_status.py` | each crypto book publishes its own `grades` object, including the sentence to print |
| `monitor.py` | the desk page; the forex half reads `trades_log.jsonl` through the same module |
| `trade_radar.py` | `/data.json` carries `record{fx, books, overall}`; the page, `/embed` and the 4-hour digest all render `line()` |

The rules, deliberately unglamorous:

* **graded rows only** — a candidate that never filled is not a win, a loss, or a denominator;
* `decisive = wins + losses`, **`win_rate = wins / decisive`**, because a void (`scratch`) is neither;
  `hit_rate = wins / graded` is printed beside it for anyone who wants voids to count against;
* **net R** is summed over graded rows, NaN-safe — a rate without its money is a marketing number;
* per-skill accuracy stays **weighted** (a fired fill counts 2×, a void 0.5×) because that is exactly what
  `self_size()` reads; the page shows both and never labels the second one a win rate;
* books are pooled by **adding counts and recomputing**, never by averaging two rates;
* a skill needs **3 records** before it is ranked at all, and an empty log prints `—`, never `0 %`.

A book whose published JSON predates the win rate is not shown as a dash: `with_line()` completes the ratio
from the counts that book itself published — the same formula, not a second one.

## Honest limitations (read before calling it "the same thing")
- **Long-only execution.** Spot crypto can't be shorted here, so short signals are *paper-graded*
  into the accuracy loop (they earn sizing trust, never fire). A futures/perp venue would be needed
  for real shorts.
- **Ledger-mode fills are simulated** against Coinbase quotes; slippage/liquidity on thin alts is
  optimistic (a fill is never priced worse than the tape, but there is no order-book depth model).
  `coinbase` mode puts the orders on the real book.
- **Stop/TP enforcement is per-cycle** (up to ~10 min reaction latency, cron jitter included).
  Fine for an M15 playbook; not scalping.
- **Cron is best-effort** — on this account it is actively throttled; see *Cadence* above before
  trusting the 10-min interval. A missed run only delays the next reconcile (stateless per cycle).
- **Outcome grading uses the last tracked price vs tp/sl** (a heuristic), not an exchange fill
  report — win/loss flags can be ±1 grade off on violent bars.
- FX & US equities stay on the Mac/MT5 build. OANDA's practice API is the natural adapter if forex
  should move here too — it's one `broker_oanda.py` away.

## Why this design survives what the Mac version suffered
| Failure mode | Mac build | v4 here |
|---|---|---|
| bridge/terminal down | cycles silently with empty quotes | job exits **red** → GitHub notification |
| stale candle window (hardcoded dates) | would trade blind | staleness guard: >3 h-old bar = ALERT |
| JSON quoted through bash | `-32700` spam, 177× | stdlib REST client, no shell at all |
| broker renames a symbol | hardcoded dict breaks | live `/asset-trading-platform/PAPER/reference/crypto` lookup |
| two writers collide | (hit us: `git push` conflict killed a run) | memory via Contents API, re-read + retry on 409 |
| state lost | Mac-local file | state lives in git history, diffable forever |

## The desk page (`tools/mac/`)

On the Mac, each book publishes `~/hermes_sentry/books/<book>.json` after every cycle and
`tools/mac/monitor.py` renders all of them — plus the MT5 forex build — into one read-only page,
`~/hermes_sentry/TRADING.html`. Entries for all three crypto books can be paused with
`~/hermes_sentry/crypto_desk_mode.json` (`{"entries_enabled": false}`), which stops new entries while
stops, exits and the graded record keep running. See `tools/mac/README.md`.
