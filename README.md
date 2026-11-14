# Sentry v4.5.1 — GitHub-native trading brain (no MT5, no Mac, no Wine)

The same checklist engine from the Mac build (`sentry_mac.py` v3.1), ported to run entirely on
**GitHub Actions**. One workflow run = one full scan cycle, every 10 minutes, 24/7 (crypto has no
weekend gap — MT5 demo servers do).

**Start here → [`STATUS.md`](STATUS.md)** — rewritten by the bot at the end of every cycle: what
venue it is on, what is resting on the book, what it holds and at what P/L, and the last 12 signals
with what happened to each one. `journal.md` is the full decision log; `STATUS.md` is the page.

```
┌─ Actions cron (*/10) ─┐   ┌─ this repo = the database ────────────┐
│ run_cycle.py          │──▶│ state.json        (orders/positions)  │
│  1. fetch klines      │   │ ledger.json       (simulated fills)   │
│  2. reconcile fills   │   │ journal.md        (every decision)    │
│  3. evaluate skills   │   │ trades_log.jsonl  (accuracy → sizing) │
│  4. size + fire       │──▶ venue: Coinbase ledger or Alpaca paper │
│  5. push_memory (API) │   └───────────────────────────────────────┘
└───────────────────────┘
```

- `sentry_core.py` — pure brain: EMA/RSI/ATR/Bollinger/pivots, playbook §12 candle engine,
  skill checklists S1/S2/S4/S18/S11, 5-point scoring, accuracy-based self-sizing ($50–$200).
- `broker_ledger.py` — default venue: Coinbase *public* candles + simulated fills in `ledger.json`.
  Zero accounts, zero secrets, nothing to rot.
- `broker.py` — optional Alpaca paper REST client (stdlib only, no pip installs).
- `run_cycle.py` — orchestrator + state machine + **loud-death guards** (exits red on stale or
  thin data, never "scan ok" on nothing) + `push_memory()` (writes memory through the Contents
  API with retry, so two runners can never conflict the way `git push` did).

## Execution modes (one config line)
- **`"execution": "coinbase"` (what ships):** Coinbase via `broker_coinbase.py` — **real orders on
  a real book**, on either Coinbase API (retail Advanced Trade or institutional Exchange; the
  presence of a passphrase picks which, see "Going live"). The key lives only in Actions Secrets.
  With no key in the runner it runs the shadow ledger on the same public data and stamps
  `venue shadow-ledger(coinbase-no-key)` into the journal line, so "did that touch real money?" is
  always answerable from the log.
- **`"execution": "okx"`:** OKX via `broker_okx.py` — real orders on perps, **0.02 %/0.05 % fees**, TP/SL
  attached to the entry order by the venue, and the short side of the checklist actually tradable.
  `vars.OKX_SIM=1` switches it to OKX's simulated-trading engine: same host, same signatures, real
  matching, **no money** — the rehearsal Coinbase cannot offer. Same no-key fallback to the shadow book.
- **`"execution": "ledger"`:** shadow book only — real prices, simulated fills in `ledger.json`.
  Paper fills are honest about price (never worse than the tape) but have no depth model.
- **`"execution": "alpaca"`:** Alpaca paper venue (resting orders on their engine). Needs
  `ALPACA_KEY_ID` + `ALPACA_SECRET`. Same brain, different venue.

## Going live on Coinbase

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
3. `config.json`: `"execution": "coinbase"` (already set) **and `"live_ack": true`**. That flag is
   deliberately a repo file edit, not an env var: pasting a key must not be enough to start
   trading, and the flip is visible in the commit history.
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

Until step 3 the bot scans, sizes, journals `GATE — …` and sends nothing. The four live gates
(`live_gate()` in `run_cycle.py`) each trace to a real defect found on this account, not ceremony:

| gate | why it exists |
|---|---|
| `live_ack: true` | a leaked secret must not be enough to trade |
| `min_grade_before_live` = 8 graded outcomes (paper counts) | the sizer scales off its own accuracy; sizing live with zero graded outcomes is a blind number |
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
