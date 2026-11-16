# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-16 08:47 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $82,783.16 · equity $99,876.72

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$68.88 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (5)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| ETH/USD | buy_stop | 1820.1129 | 3.86894 | $7,042 | $75.00 | 1808.39 | +0.65% | 6 min |
| LINK/USD | buy_stop | 9.1586365 | 601.31 | $5,507 | $75.00 | 9.125 | +0.37% | 6 min |
| LTC/USD | buy_stop | 44.842914 | 118.073 | $5,295 | $75.00 | 44.57 | +0.61% | 6 min |
| SOL/USD | buy_stop | 71.529055 | 75.2489 | $5,382 | $75.00 | 71.02 | +0.72% | 6 min |
| XRP/USD | buy_stop | 0.95763808 | 6232.71 | $5,969 | $75.00 | 0.9557 | +0.20% | 6 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (1)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BTC/USD | 0.069084 | 63278.87 | 64535.48 | $86.81 | 63069.244 | 66371.462 | +1.74R |

## Last 12 signals (178 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-16 08:47 | AVAX/USD | S18-rsi2-short | 4/5 | 7.166 | 7.2939908 | 7.0060115 | $100.00 | paper-graded (spot cannot short) |
| 11-16 08:42 | AVAX/USD | C-M15-three-outside-down | 5/5 | 7.1083341 | 7.1956648 | 6.9773381 | $125.00 | paper-graded (spot cannot short) |
| 11-16 08:42 | AVAX/USD | C-M15-marubozu | 5/5 | 7.1083341 | 7.1956648 | 6.9773381 | $125.00 | paper-graded (spot cannot short) |
| 11-16 08:42 | AVAX/USD | S13-ichimoku-short | 4/5 | 7.1400011 | 7.2309977 | 6.9213502 | $100.00 | paper-graded (spot cannot short) |
| 11-16 08:42 | BCH/USD | C-M15-three-outside-down | 5/5 | 206.63229 | 208.54428 | 203.76429 | $125.00 | paper-graded (spot cannot short) |
| 11-16 08:42 | BCH/USD | C-M15-marubozu | 5/5 | 206.63229 | 208.54428 | 203.76429 | $125.00 | paper-graded (spot cannot short) |
| 11-16 08:42 | LTC/USD | C-M15-evening-star | 5/5 | 44.567086 | 44.982285 | 43.944287 | $125.00 | paper-graded (spot cannot short) |
| 11-16 08:42 | LTC/USD | C-M15-marubozu | 5/5 | 44.567086 | 44.982285 | 43.944287 | $125.00 | paper-graded (spot cannot short) |
| 11-16 08:42 | LTC/USD | C-H1-tweezer-bottom | 3/5 | 44.842914 | 44.207715 | 45.795713 | $75.00 | order placed |
| 11-16 08:42 | LTC/USD | S13-ichimoku-short | 4/5 | 44.510629 | 45.188742 | 43.425891 | $100.00 | paper-graded (spot cannot short) |
| 11-16 08:42 | LINK/USD | C-M15-three-inside-down | 5/5 | 9.1053635 | 9.1900913 | 8.9782719 | $125.00 | paper-graded (spot cannot short) |
| 11-16 08:42 | LINK/USD | C-M15-marubozu | 5/5 | 9.1053635 | 9.1900913 | 8.9782719 | $125.00 | paper-graded (spot cannot short) |

## Accuracy so far

1 graded outcomes (0 win / 1 loss) · win rate 0% · avg -0.61R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 0 new order(s), 10 symbols scanned

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
