# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-25 23:08 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-178,050.94 · equity $97,668.18

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$331.34 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (4)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| ETH/USD | buy_limit | 1681.73 | 4.06209 | $6,831 | $100.00 | 1685.97 | -0.25% | 0 min |
| ETH/USD | buy_stop | 1689.5815 | 9.00073 | $15,207 | $100.00 | 1685.97 | +0.21% | 0 min |
| SOL/USD | buy_limit | 70.3 | 89.9789 | $6,326 | $100.00 | 70.53 | -0.33% | 0 min |
| XRP/USD | buy_limit | 0.9338 | 5578.33 | $5,209 | $75.00 | 0.9366 | -0.30% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (740 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-25 23:08 | AVAX/USD | S21-pivot-S1-short | 4/5 | 6.6436985 | 6.9383333 | 6.0783333 | $100.00 | paper-graded (spot cannot short) |
| 11-25 23:08 | BCH/USD | C-H1-tweezer-top | 3/5 | 203.34863 | 205.61843 | 199.94391 | $75.00 | paper-graded (spot cannot short) |
| 11-25 23:08 | BCH/USD | S22-rsi-bear-div | 4/5 | 202.71863 | 205.61843 | 198.36891 | $100.00 | paper-graded (spot cannot short) |
| 11-25 23:08 | LINK/USD | S22-rsi-bear-div | 4/5 | 9.0036502 | 9.1613746 | 8.7670635 | $100.00 | paper-graded (spot cannot short) |
| 11-25 23:08 | ADA/USD | S22-rsi-bear-div | 4/5 | 0.14509528 | 0.14841181 | 0.14012048 | $100.00 | paper-graded (spot cannot short) |
| 11-25 23:08 | DOGE/USD | S23-upthrust-short | 4/5 | 0.05579214 | 0.05653964 | 0.054664 | $100.00 | paper-graded (spot cannot short) |
| 11-25 23:08 | SOL/USD | S21-pivot-S1-short | 4/5 | 70.720719 | 74.636667 | 63.166667 | $100.00 | paper-graded (spot cannot short) |
| 11-25 23:08 | SOL/USD | S18-rsi2-long | 4/5 | 70.3 | 69.188628 | 71.689215 | $100.00 | order placed |
| 11-25 23:08 | XRP/USD | C-H1-gravestone | 3/5 | 0.93937959 | 0.95120102 | 0.92164746 | $75.00 | paper-graded (spot cannot short) |
| 11-25 23:08 | XRP/USD | C-H1-shooting-star | 3/5 | 0.93937959 | 0.95120102 | 0.92164746 | $75.00 | paper-graded (spot cannot short) |
| 11-25 23:08 | XRP/USD | S23-upthrust-short | 4/5 | 0.93937959 | 0.95120102 | 0.92158572 | $100.00 | paper-graded (spot cannot short) |
| 11-25 23:08 | XRP/USD | S18-rsi2-long | 3/5 | 0.9338 | 0.92035512 | 0.95060611 | $75.00 | order placed |

## Accuracy so far

14 graded outcomes (5 win / 8 loss / 1 scratch) · win rate 38% · avg -0.05R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 4 new order(s), 10 symbols scanned

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
