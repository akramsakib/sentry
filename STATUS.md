# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-18 20:38 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $66,291.66 · equity $99,094.03

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$176.00 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (3)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| AVAX/USD | buy_limit | 6.896 | 576.641 | $3,977 | $50.00 | 6.929 | -0.48% | 227 min |
| BCH/USD | buy_stop | 207.43764 | 27.4278 | $5,690 | $56.00 | 206.03 | +0.68% | 244 min |
| ETH/USD | buy_stop | 1778.1605 | 1.77043 | $3,148 | $50.00 | 1749.47 | +1.64% | 310 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (3)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| DOGE/USD | 157867 | 0.05807 | 0.05844 | $58.41 | 0.05790527 | 0.0593965 | +1.04R |
| SOL/USD | 108.486 | 72.53 | 72.92 | $42.31 | 72.273804 | 74.428 | +0.76R |
| XRP/USD | 4643.61 | 0.95972892 | 0.966 | $29.12 | 0.94357771 | 0.97833374 | +0.39R |

## Last 12 signals (424 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-18 19:08 | ADA/USD | S13-ichimoku-short | 4/5 | 0.15163434 | 0.15328132 | 0.14800364 | $62.00 | paper-graded (spot cannot short) |
| 11-18 19:08 | DOGE/USD | C-M15-three-outside-up | 4/5 | 0.0590554 | 0.05856651 | 0.05978873 | $62.00 | not fired (guard/duplicate) |
| 11-18 19:08 | DOGE/USD | C-M15-tweezer-bottom | 4/5 | 0.0590554 | 0.05856651 | 0.05978873 | $62.00 | not fired (guard/duplicate) |
| 11-18 19:08 | DOGE/USD | C-M15-marubozu | 4/5 | 0.0590554 | 0.05856651 | 0.05978873 | $62.00 | not fired (guard/duplicate) |
| 11-18 19:08 | DOGE/USD | C-H1-bull-engulfing | 4/5 | 0.0593554 | 0.05798651 | 0.06140873 | $62.00 | not fired (guard/duplicate) |
| 11-18 19:08 | SOL/USD | C-M15-marubozu | 4/5 | 74.132769 | 73.398078 | 75.234805 | $62.00 | not fired (guard/duplicate) |
| 11-18 19:08 | SOL/USD | C-H1-bull-engulfing | 3/5 | 74.332769 | 72.488078 | 77.099805 | $50.00 | not fired (guard/duplicate) |
| 11-18 19:08 | XRP/USD | C-M15-three-outside-up | 4/5 | 0.98254206 | 0.97454485 | 0.99453788 | $62.00 | not fired (guard/duplicate) |
| 11-18 16:51 | AVAX/USD | S18-ma-revert-long | 3/5 | 6.896 | 6.8092909 | 7.1147345 | $50.00 | order placed |
| 11-18 16:51 | LINK/USD | S21-pivot-S1-short | 4/5 | 8.9527964 | 9.1606667 | 8.5656667 | $67.00 | paper-graded (spot cannot short) |
| 11-18 16:34 | BCH/USD | S16-inside-short | 4/5 | 205.69236 | 207.73409 | 202.92546 | $75.00 | paper-graded (spot cannot short) |
| 11-18 16:34 | BCH/USD | S16-inside-long | 3/5 | 207.43764 | 205.39591 | 210.20454 | $56.00 | order placed |

## Accuracy so far

11 graded outcomes (2 win / 8 loss / 1 scratch) · win rate 20% · avg -0.37R · sizing today: score 3 -> $50.00 · score 4 -> $50.00 · score 5 -> $62.00

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
