# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-23 03:42 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-78,548.33 · equity $99,273.58

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$275.85 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (6)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_stop | 61476.2 | 0.0962312 | $5,916 | $100.00 | 61409.2 | +0.11% | 0 min |
| DOGE/USD | buy_stop | 0.05547 | 94795.7 | $5,258 | $100.00 | 0.05534 | +0.23% | 0 min |
| SOL/USD | buy_stop | 71.609449 | 42.8976 | $3,072 | $75.00 | 71.32 | +0.41% | 0 min |
| XRP/USD | buy_stop | 0.9335 | 4870.07 | $4,546 | $100.00 | 0.9323 | +0.13% | 0 min |
| XRP/USD | buy_stop | 0.9335 | 4870.07 | $4,546 | $100.00 | 0.9323 | +0.13% | 0 min |
| XRP/USD | buy_stop | 0.9335 | 4870.07 | $4,546 | $100.00 | 0.9323 | +0.13% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (631 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-23 03:42 | AVAX/USD | C-H1-marubozu | 5/5 | 6.5943514 | 6.6731215 | 6.4761963 | $125.00 | paper-graded (spot cannot short) |
| 11-23 03:42 | BCH/USD | C-H1-marubozu | 5/5 | 196.68612 | 199.02969 | 193.17077 | $125.00 | paper-graded (spot cannot short) |
| 11-23 03:42 | LINK/USD | C-H1-tweezer-top | 5/5 | 8.7748513 | 8.8628717 | 8.6428208 | $125.00 | paper-graded (spot cannot short) |
| 11-23 03:42 | LINK/USD | C-H1-bear-engulfing | 5/5 | 8.7748513 | 8.8628717 | 8.6428208 | $125.00 | paper-graded (spot cannot short) |
| 11-23 03:42 | DOGE/USD | C-M15-marubozu | 4/5 | 0.05516596 | 0.0544151 | 0.05629225 | $100.00 | order placed |
| 11-23 03:42 | SOL/USD | C-H1-evening-star | 5/5 | 70.230367 | 70.999082 | 69.077295 | $125.00 | paper-graded (spot cannot short) |
| 11-23 03:42 | SOL/USD | C-H1-tweezer-top | 5/5 | 70.230367 | 70.999082 | 69.077295 | $125.00 | paper-graded (spot cannot short) |
| 11-23 03:42 | SOL/USD | S13-ichimoku-long | 3/5 | 71.609449 | 69.861102 | 72.831921 | $75.00 | order placed |
| 11-23 03:42 | XRP/USD | C-M15-three-inside-up | 4/5 | 0.92707343 | 0.91296642 | 0.94823396 | $100.00 | order placed |
| 11-23 03:42 | XRP/USD | C-M15-morning-star | 4/5 | 0.92707343 | 0.91296642 | 0.94823396 | $100.00 | order placed |
| 11-23 03:42 | XRP/USD | C-M15-bull-engulfing | 4/5 | 0.92707343 | 0.91296642 | 0.94823396 | $100.00 | order placed |
| 11-23 03:42 | BTC/USD | C-M15-morning-star | 4/5 | 61267.266 | 60437.036 | 62512.611 | $100.00 | order placed |

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
