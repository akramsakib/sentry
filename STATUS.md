# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-14 20:10 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $99,780.60 · equity $99,780.60

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$60.38 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (6)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| ADA/USD | buy_stop | 0.15745624 | 32026 | $5,043 | $75.00 | 0.1542 | +2.11% | 240 min |
| BTC/USD | buy_stop | 65759.923 | 0.089044 | $5,856 | $75.00 | 65674.52 | +0.13% | 240 min |
| ETH/USD | buy_stop | 1841.7081 | 2.63387 | $4,851 | $50.00 | 1833.86 | +0.43% | 0 min |
| ETH/USD | buy_stop | 1841.7081 | 2.63387 | $4,851 | $50.00 | 1833.86 | +0.43% | 0 min |
| SOL/USD | buy_stop | 72.591023 | 59.2712 | $4,303 | $50.00 | 72.18 | +0.57% | 0 min |
| XRP/USD | buy_stop | 0.9568033 | 5548.44 | $5,309 | $50.00 | 0.9528 | +0.42% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (48 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-14 20:10 | BCH/USD | C-H1-bear-engulfing | 3/5 | 205.78705 | 209.73237 | 199.86909 | $50.00 | paper-graded (spot cannot short) |
| 11-14 20:10 | SOL/USD | C-M15-bull-engulfing | 4/5 | 72.591023 | 71.747443 | 73.856392 | $50.00 | order placed |
| 11-14 20:10 | XRP/USD | C-M15-morning-star | 3/5 | 0.9568033 | 0.94779175 | 0.97032062 | $50.00 | order placed |
| 11-14 20:10 | ETH/USD | C-M15-morning-star | 3/5 | 1841.7081 | 1822.7247 | 1870.1833 | $50.00 | order placed |
| 11-14 20:10 | ETH/USD | C-M15-piercing-line | 3/5 | 1841.7081 | 1822.7247 | 1870.1833 | $50.00 | order placed |
| 11-14 16:09 | AVAX/USD | C-H1-three-crows | 4/5 | 7.5988914 | 7.9507716 | 7.0710711 | $100.00 | paper-graded (spot cannot short) |
| 11-14 16:09 | LTC/USD | C-H1-three-crows | 4/5 | 46.099076 | 47.602309 | 43.844227 | $100.00 | paper-graded (spot cannot short) |
| 11-14 16:09 | LINK/USD | S11-dc55-short | 4/5 | 9.4783612 | 9.5668327 | 9.2129467 | $100.00 | paper-graded (spot cannot short) |
| 11-14 16:09 | LINK/USD | S11-dc20-short | 4/5 | 9.4783612 | 9.5668327 | 9.2129467 | $100.00 | paper-graded (spot cannot short) |
| 11-14 16:09 | ADA/USD | C-M15-hammer/takuri | 3/5 | 0.15745624 | 0.15511439 | 0.16096902 | $75.00 | order placed |
| 11-14 16:09 | ADA/USD | C-H1-three-crows | 4/5 | 0.15671015 | 0.16126464 | 0.14987841 | $100.00 | paper-graded (spot cannot short) |
| 11-14 16:09 | DOGE/USD | S11-dc55-short | 4/5 | 0.06193122 | 0.06248271 | 0.06027674 | $100.00 | paper-graded (spot cannot short) |

## Accuracy so far

1 graded outcomes (0 win / 1 loss) · win rate 0% · avg -0.61R · sizing today: score 3 -> $50.00 · score 4 -> $50.00 · score 5 -> $62.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 4 new order(s), 10 symbols scanned

| line starts with | meaning |
|---|---|
| `CANDIDATE(score n/5)` | a skill matched and was scored, but no order was sent (short on spot, duplicate, below the fire floor) |
| `ORDER SENT` | an order was placed on the venue named in the summary line |
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

_On a live venue the exchange is the authority: the orders above are what Sentry believes it placed, the Coinbase app's Orders/History tab is what actually exists._
