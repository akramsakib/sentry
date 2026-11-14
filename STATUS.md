# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-14 21:15 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $99,780.60 · equity $99,780.60

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$60.38 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (6)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| ADA/USD | buy_stop | 0.15745624 | 32026 | $5,043 | $75.00 | 0.1458 | +7.99% | 306 min |
| BTC/USD | buy_stop | 65759.923 | 0.089044 | $5,856 | $75.00 | 64248.3 | +2.35% | 306 min |
| ETH/USD | buy_stop | 1841.7081 | 2.63387 | $4,851 | $50.00 | 1761.25 | +4.57% | 65 min |
| ETH/USD | buy_stop | 1841.7081 | 2.63387 | $4,851 | $50.00 | 1761.25 | +4.57% | 65 min |
| SOL/USD | buy_stop | 72.591023 | 59.2712 | $4,303 | $50.00 | 69.58 | +4.33% | 65 min |
| XRP/USD | buy_stop | 0.9568033 | 5548.44 | $5,309 | $50.00 | 0.9156 | +4.50% | 65 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (59 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-14 21:06 | AVAX/USD | S13-ichimoku-short | 4/5 | 7.1492601 | 7.9604798 | 6.8658144 | $50.00 | paper-graded (spot cannot short) |
| 11-14 21:06 | BCH/USD | C-M15-three-outside-down | 5/5 | 203.07406 | 207.66486 | 196.18785 | $62.00 | paper-graded (spot cannot short) |
| 11-14 21:06 | BCH/USD | C-M15-tweezer-top | 5/5 | 203.07406 | 207.66486 | 196.18785 | $62.00 | paper-graded (spot cannot short) |
| 11-14 21:06 | BCH/USD | C-M15-bear-engulfing | 5/5 | 203.07406 | 207.66486 | 196.18785 | $62.00 | paper-graded (spot cannot short) |
| 11-14 21:06 | BCH/USD | S13-ichimoku-short | 4/5 | 201.40108 | 217.30783 | 193.89924 | $50.00 | paper-graded (spot cannot short) |
| 11-14 21:06 | LTC/USD | S13-ichimoku-short | 4/5 | 44.370899 | 47.708201 | 42.879857 | $50.00 | paper-graded (spot cannot short) |
| 11-14 21:06 | LINK/USD | S13-ichimoku-short | 4/5 | 8.7944732 | 9.5785536 | 8.4729403 | $50.00 | paper-graded (spot cannot short) |
| 11-14 21:06 | DOGE/USD | C-M15-three-outside-down | 5/5 | 0.05844613 | 0.05968967 | 0.05658081 | $62.00 | paper-graded (spot cannot short) |
| 11-14 21:06 | DOGE/USD | C-M15-tweezer-top | 5/5 | 0.05844613 | 0.05968967 | 0.05658081 | $62.00 | paper-graded (spot cannot short) |
| 11-14 21:06 | DOGE/USD | C-M15-bear-engulfing | 5/5 | 0.05844613 | 0.05968967 | 0.05658081 | $62.00 | paper-graded (spot cannot short) |
| 11-14 21:06 | DOGE/USD | S13-ichimoku-short | 4/5 | 0.0576742 | 0.06288161 | 0.05554486 | $50.00 | paper-graded (spot cannot short) |
| 11-14 20:10 | BCH/USD | C-H1-bear-engulfing | 3/5 | 205.78705 | 209.73237 | 199.86909 | $50.00 | paper-graded (spot cannot short) |

## Accuracy so far

1 graded outcomes (0 win / 1 loss) · win rate 0% · avg -0.61R · sizing today: score 3 -> $50.00 · score 4 -> $50.00 · score 5 -> $62.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 0 new order(s), 10 symbols scanned

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
