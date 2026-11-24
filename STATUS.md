# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-24 01:15 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-131,534.06 · equity $102,185.32

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$312.85 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (6)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| ADA/USD | buy_stop | 0.1498 | 26804.1 | $4,015 | $100.00 | 0.1498 | +0.00% | 0 min |
| ADA/USD | buy_stop | 0.1498 | 26804.1 | $4,015 | $100.00 | 0.1498 | +0.00% | 0 min |
| BTC/USD | buy_stop | 61517.9 | 0.111008 | $6,829 | $75.00 | 61517.9 | +0.00% | 0 min |
| ETH/USD | buy_stop | 1718.46 | 4.2404 | $7,287 | $75.00 | 1718.46 | +0.00% | 0 min |
| SOL/USD | buy_stop | 72.4 | 72.2571 | $5,231 | $75.00 | 72.4 | +0.00% | 0 min |
| SOL/USD | buy_stop | 72.4 | 107.456 | $7,780 | $75.00 | 72.4 | +0.00% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (653 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-24 01:15 | AVAX/USD | C-M15-tweezer-top | 5/5 | 6.7858984 | 6.8437541 | 6.6991147 | $125.00 | paper-graded (spot cannot short) |
| 11-24 01:15 | AVAX/USD | C-M15-bear-engulfing | 5/5 | 6.7858984 | 6.8437541 | 6.6991147 | $125.00 | paper-graded (spot cannot short) |
| 11-24 01:15 | LTC/USD | C-M15-evening-star | 4/5 | 41.467057 | 41.782358 | 40.994104 | $100.00 | paper-graded (spot cannot short) |
| 11-24 01:15 | LINK/USD | C-M15-marubozu | 5/5 | 9.023384 | 9.0940399 | 8.9174002 | $125.00 | paper-graded (spot cannot short) |
| 11-24 01:15 | ADA/USD | C-H1-tweezer-bottom | 4/5 | 0.14871231 | 0.14606923 | 0.15267692 | $100.00 | order placed |
| 11-24 01:15 | ADA/USD | C-H1-bull-engulfing | 4/5 | 0.14871231 | 0.14606923 | 0.15267692 | $100.00 | order placed |
| 11-24 01:15 | DOGE/USD | C-M15-tweezer-top | 4/5 | 0.05644222 | 0.05686446 | 0.05580886 | $100.00 | paper-graded (spot cannot short) |
| 11-24 01:15 | SOL/USD | C-M15-dragonfly | 3/5 | 72.287184 | 71.70204 | 73.164899 | $75.00 | order placed |
| 11-24 01:15 | SOL/USD | C-H1-tweezer-bottom | 3/5 | 72.327184 | 71.36204 | 73.774899 | $75.00 | order placed |
| 11-24 01:15 | SOL/USD | S18-rsi2-short | 4/5 | 72.4 | 73.686206 | 70.792242 | $100.00 | paper-graded (spot cannot short) |
| 11-24 01:15 | ETH/USD | C-M15-hammer/takuri | 3/5 | 1713.8008 | 1700.773 | 1733.3425 | $75.00 | order placed |
| 11-24 01:15 | ETH/USD | S13-ichimoku-short | 4/5 | 1715.0238 | 1777.0924 | 1668.0623 | $100.00 | paper-graded (spot cannot short) |

## Accuracy so far

14 graded outcomes (5 win / 8 loss / 1 scratch) · win rate 38% · avg -0.05R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 6 new order(s), 10 symbols scanned

| line starts with | meaning |
|---|---|
| `CANDIDATE(score n/5)` | a skill matched and was scored, but no order was sent (short on spot, duplicate, below the fire floor) |
| `ORDER SENT` | an order was placed ON THE VENUE (only possible with a live key and money moving) |
| `ORDER BOOKED` | the same order, in this machine's ledger — with no key nothing was sent anywhere |
| `RE-ANCHORED` | the trigger was already through the tape, so entry moved to market and R was recomputed |
| `FILL` | an entry filled — now a position, with its stop armed on the venue |
| `EXIT` / `CLOSED` | stop or target hit; P&L booked and the signal graded win/loss |
| `SKIP` / `CAPPED` / `LIVE RISK CLAMP` | a guard refused or resized the trade; reason is inline |
| `GATE` | live venue armed but new entries blocked; reason is inline |
| `EXPIRED` | a resting entry went older than `pending_ttl_h` and was cancelled — the setup is stale |
| `ALERT` | the cycle died. The run is red — open its log, nothing was skipped on purpose |

## Read it from a terminal

```bash
curl -s https://raw.githubusercontent.com/akramsakib/sentry/main/STATUS.md | head -40            # this page
curl -s https://raw.githubusercontent.com/akramsakib/sentry/main/journal.md | tail -20           # every decision, newest last
curl -s https://raw.githubusercontent.com/akramsakib/sentry/main/ledger.json | python3 -m json.tool   # the book itself
curl -s https://raw.githubusercontent.com/akramsakib/sentry/main/trades_log.jsonl | tail -5      # one line per signal
```

_On a live venue the exchange is the authority: the orders above are what Sentry believes it placed, the venue's own Orders/Positions tab (OKX app or web) is what actually exists._
