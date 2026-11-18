# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-18 16:03 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $66,662.39 · equity $99,370.14

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$142.93 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (2)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_limit | 63033.2 | 0.257612 | $16,238 | $75.00 | 63100.7 | -0.11% | 9 min |
| ETH/USD | buy_stop | 1778.1605 | 1.77043 | $3,148 | $50.00 | 1767.62 | +0.60% | 35 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (4)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BTC/USD | 0.154567 | 62972.71 | 62972.71 | $0.00 | 62547.974 | 64315.683 | +0.00R |
| DOGE/USD | 54931.8 | 0.05911149 | 0.05866 | $-24.80 | 0.05820127 | 0.06047682 | -0.50R |
| SOL/USD | 54.3458 | 71.398586 | 73.22 | $98.99 | 70.018534 | 72.918795 | +1.32R |
| XRP/USD | 4643.61 | 0.95972892 | 0.976 | $75.56 | 0.94357771 | 0.97833374 | +1.01R |

## Last 12 signals (406 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-18 16:03 | AVAX/USD | C-M15-three-outside-down | 4/5 | 6.9483291 | 7.0646773 | 6.7738068 | $67.00 | paper-graded (spot cannot short) |
| 11-18 16:03 | AVAX/USD | C-M15-tweezer-top | 4/5 | 6.9483291 | 7.0646773 | 6.7738068 | $67.00 | paper-graded (spot cannot short) |
| 11-18 16:03 | AVAX/USD | C-M15-bear-engulfing | 4/5 | 6.9483291 | 7.0646773 | 6.7738068 | $67.00 | paper-graded (spot cannot short) |
| 11-18 16:03 | AVAX/USD | S21-pivot-S1-short | 4/5 | 6.9703291 | 7.146 | 6.645 | $67.00 | paper-graded (spot cannot short) |
| 11-18 16:03 | AVAX/USD | S13-ichimoku-short | 4/5 | 6.9449936 | 7.1565127 | 6.76724 | $67.00 | paper-graded (spot cannot short) |
| 11-18 16:03 | BCH/USD | S3-momentum-short | 4/5 | 205.91236 | 209.81527 | 198.30418 | $67.00 | paper-graded (spot cannot short) |
| 11-18 16:03 | BCH/USD | S13-ichimoku-short | 4/5 | 206.28355 | 209.70291 | 202.23201 | $67.00 | paper-graded (spot cannot short) |
| 11-18 16:03 | LINK/USD | S13-ichimoku-short | 4/5 | 8.9936946 | 9.1951109 | 8.798187 | $67.00 | paper-graded (spot cannot short) |
| 11-18 16:03 | ADA/USD | C-H1-three-outside-down | 5/5 | 0.15142661 | 0.15473347 | 0.14646633 | $83.00 | paper-graded (spot cannot short) |
| 11-18 16:03 | ADA/USD | C-H1-bear-engulfing | 5/5 | 0.15142661 | 0.15473347 | 0.14646633 | $83.00 | paper-graded (spot cannot short) |
| 11-18 16:03 | DOGE/USD | C-H1-bear-harami | 3/5 | 0.05858088 | 0.0598778 | 0.05663549 | $50.00 | not fired (guard/duplicate) |
| 11-18 16:03 | DOGE/USD | S23-spring-long | 3/5 | 0.05978912 | 0.0584922 | 0.06180508 | $50.00 | not fired (guard/duplicate) |

## Accuracy so far

8 graded outcomes (1 win / 6 loss / 1 scratch) · win rate 14% · avg -0.38R · sizing today: score 3 -> $56.00 · score 4 -> $75.00 · score 5 -> $94.00

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
