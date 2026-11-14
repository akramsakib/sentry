# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-14 22:12 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $99,780.60 · equity $99,780.60

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$62.57 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (5)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_limit | 63793 | 0.069084 | $4,407 | $50.00 | 64422.1 | -0.98% | 0 min |
| ETH/USD | buy_stop | 1841.7081 | 2.63387 | $4,851 | $50.00 | 1772.42 | +3.91% | 123 min |
| ETH/USD | buy_stop | 1841.7081 | 2.63387 | $4,851 | $50.00 | 1772.42 | +3.91% | 123 min |
| SOL/USD | buy_stop | 72.591023 | 59.2712 | $4,303 | $50.00 | 69.87 | +3.89% | 123 min |
| XRP/USD | buy_stop | 0.9568033 | 5548.44 | $5,309 | $50.00 | 0.9099 | +5.15% | 123 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (71 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-14 22:12 | BCH/USD | C-H1-three-outside-down | 5/5 | 199.12627 | 209.28933 | 183.88167 | $62.00 | paper-graded (spot cannot short) |
| 11-14 22:12 | BCH/USD | C-H1-tweezer-top | 5/5 | 199.12627 | 209.28933 | 183.88167 | $62.00 | paper-graded (spot cannot short) |
| 11-14 22:12 | BCH/USD | S11-dc55-short | 4/5 | 204.13627 | 206.8224 | 196.07786 | $50.00 | paper-graded (spot cannot short) |
| 11-14 22:12 | BCH/USD | S11-dc20-short | 4/5 | 204.13627 | 206.8224 | 196.07786 | $50.00 | paper-graded (spot cannot short) |
| 11-14 22:12 | LTC/USD | S3-momentum-short | 4/5 | 44.013676 | 45.832648 | 40.452055 | $50.00 | paper-graded (spot cannot short) |
| 11-14 22:12 | ADA/USD | S3-momentum-short | 4/5 | 0.14660835 | 0.1553833 | 0.12935011 | $50.00 | paper-graded (spot cannot short) |
| 11-14 22:12 | ADA/USD | S13-ichimoku-short | 4/5 | 0.14446253 | 0.16042495 | 0.13848373 | $50.00 | paper-graded (spot cannot short) |
| 11-14 22:12 | BTC/USD | C-H1-three-outside-down | 5/5 | 64371.624 | 66034.539 | 61877.252 | $62.00 | paper-graded (spot cannot short) |
| 11-14 22:12 | BTC/USD | C-H1-tweezer-top | 5/5 | 64371.624 | 66034.539 | 61877.252 | $62.00 | paper-graded (spot cannot short) |
| 11-14 22:12 | BTC/USD | C-H1-bear-engulfing | 5/5 | 64371.624 | 66034.539 | 61877.252 | $62.00 | paper-graded (spot cannot short) |
| 11-14 22:12 | BTC/USD | S13-ichimoku-short | 4/5 | 63684.437 | 66986.627 | 62200.736 | $50.00 | paper-graded (spot cannot short) |
| 11-14 22:12 | BTC/USD | S18-ma-revert-long | 3/5 | 63793 | 63069.244 | 66371.462 | $50.00 | order placed |

## Accuracy so far

1 graded outcomes (0 win / 1 loss) · win rate 0% · avg -0.61R · sizing today: score 3 -> $50.00 · score 4 -> $50.00 · score 5 -> $62.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 1 new order(s), 10 symbols scanned

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

_On a live venue the exchange is the authority: the orders above are what Sentry believes it placed, the venue's own Orders/Positions tab (OKX app or web) is what actually exists._
