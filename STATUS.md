# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-18 15:54 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $76,400.78 · equity $99,393.30

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$138.07 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (3)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_limit | 63033.2 | 0.257612 | $16,238 | $75.00 | 63268.7 | -0.37% | 0 min |
| BTC/USD | buy_limit | 63033.2 | 0.154567 | $9,743 | $75.00 | 63268.7 | -0.37% | 0 min |
| ETH/USD | buy_stop | 1778.1605 | 1.77043 | $3,148 | $50.00 | 1767.37 | +0.61% | 26 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (3)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| DOGE/USD | 54931.8 | 0.05911149 | 0.05869 | $-23.15 | 0.05820127 | 0.06047682 | -0.46R |
| SOL/USD | 54.3458 | 71.398586 | 73.49 | $113.66 | 70.018534 | 72.918795 | +1.52R |
| XRP/USD | 4643.61 | 0.95972892 | 0.9754 | $72.77 | 0.94357771 | 0.97833374 | +0.97R |

## Last 12 signals (392 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-18 15:54 | SOL/USD | C-M15-evening-star | 4/5 | 73.617119 | 74.487203 | 72.311992 | $100.00 | not fired (guard/duplicate) |
| 11-18 15:54 | BTC/USD | S18-ma-revert-long | 3/5 | 63033.2 | 62547.974 | 64315.683 | $75.00 | order placed |
| 11-18 15:54 | BTC/USD | S4-band-fade-long | 3/5 | 63654.844 | 62742.065 | 64364.375 | $75.00 | order placed |
| 11-18 15:36 | BCH/USD | S22-rsi-bear-div | 4/5 | 206.78401 | 209.90998 | 202.09505 | $75.00 | paper-graded (spot cannot short) |
| 11-18 15:36 | BCH/USD | S2-breakdown-short | 4/5 | 206.42002 | 210.09998 | 200.90008 | $75.00 | paper-graded (spot cannot short) |
| 11-18 15:36 | LTC/USD | C-M15-tweezer-top | 5/5 | 43.849228 | 44.281931 | 43.200172 | $94.00 | paper-graded (spot cannot short) |
| 11-18 15:36 | LTC/USD | C-M15-bear-engulfing | 5/5 | 43.849228 | 44.281931 | 43.200172 | $94.00 | paper-graded (spot cannot short) |
| 11-18 15:36 | LTC/USD | S22-rsi-bear-div | 4/5 | 43.849228 | 44.571931 | 42.765172 | $75.00 | paper-graded (spot cannot short) |
| 11-18 15:36 | LINK/USD | C-M15-bear-harami | 4/5 | 9.0618756 | 9.149811 | 8.9299724 | $75.00 | paper-graded (spot cannot short) |
| 11-18 15:36 | LINK/USD | S22-rsi-bear-div | 4/5 | 9.0618756 | 9.196811 | 8.8594724 | $75.00 | paper-graded (spot cannot short) |
| 11-18 15:36 | ADA/USD | C-M15-tweezer-top | 4/5 | 0.15183558 | 0.15341104 | 0.14947239 | $75.00 | not fired (guard/duplicate) |
| 11-18 15:36 | DOGE/USD | S22-rsi-bear-div | 4/5 | 0.05895402 | 0.05986994 | 0.05758014 | $75.00 | not fired (guard/duplicate) |

## Accuracy so far

8 graded outcomes (1 win / 6 loss / 1 scratch) · win rate 14% · avg -0.38R · sizing today: score 3 -> $50.00 · score 4 -> $67.00 · score 5 -> $83.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 2 new order(s), 10 symbols scanned

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
