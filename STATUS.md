# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-26 23:27 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-227,633.00 · equity $100,371.71

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$358.58 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (3)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BCH/USD | buy_stop | 210.60611 | 49.2966 | $10,382 | $75.00 | 209.36 | +0.60% | 0 min |
| DOGE/USD | buy_limit | 0.05637726 | 292204 | $16,474 | $75.00 | 0.05633 | +0.08% | 0 min |
| LTC/USD | buy_stop | 44.260085 | 203.958 | $9,027 | $100.00 | 43.75 | +1.17% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (3)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| ETH/USD | 9.00073 | 1689.5815 | 1685.17 | $-39.71 | 1678.4713 | 1706.2468 | -0.40R |
| SOL/USD | 89.9789 | 70.29 | 70.83 | $48.59 | 69.188628 | 71.689215 | +0.49R |
| XRP/USD | 5578.33 | 0.9326 | 0.9411 | $47.42 | 0.92035512 | 0.95060611 | +0.63R |

## Last 12 signals (785 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-26 23:27 | BCH/USD | C-M15-hammer/takuri | 3/5 | 210.60611 | 209.08471 | 212.88822 | $75.00 | order placed |
| 11-26 23:27 | LTC/USD | C-H1-three-soldiers | 4/5 | 44.260085 | 43.769787 | 44.995532 | $100.00 | order placed |
| 11-26 23:27 | ADA/USD | S22-rsi-bear-div | 4/5 | 0.14825492 | 0.15156271 | 0.14329323 | $100.00 | paper-graded (spot cannot short) |
| 11-26 23:27 | DOGE/USD | C-M15-three-outside-down | 4/5 | 0.0563551 | 0.05678225 | 0.05571436 | $100.00 | paper-graded (spot cannot short) |
| 11-26 23:27 | DOGE/USD | S4-band-fade-long | 3/5 | 0.05637726 | 0.05612059 | 0.056744 | $75.00 | order placed |
| 11-26 23:27 | SOL/USD | C-M15-three-inside-down | 5/5 | 70.80744 | 71.436399 | 69.864002 | $125.00 | not fired (guard/duplicate) |
| 11-26 23:27 | XRP/USD | C-M15-evening-star | 5/5 | 0.94434535 | 0.95128663 | 0.93393344 | $125.00 | not fired (guard/duplicate) |
| 11-26 23:27 | XRP/USD | S4-band-fade-long | 3/5 | 0.94585298 | 0.9384721 | 0.952255 | $75.00 | not fired (guard/duplicate) |
| 11-26 23:27 | ETH/USD | C-M15-tweezer-top | 5/5 | 1688.7388 | 1701.8131 | 1669.1274 | $125.00 | not fired (guard/duplicate) |
| 11-26 23:27 | BTC/USD | C-M15-three-inside-down | 5/5 | 60386.234 | 60771.516 | 59808.31 | $125.00 | paper-graded (spot cannot short) |
| 11-26 23:27 | BTC/USD | C-H1-shooting-star | 4/5 | 60688.934 | 61096.416 | 60077.71 | $100.00 | paper-graded (spot cannot short) |
| 11-26 23:27 | BTC/USD | S23-upthrust-short | 4/5 | 60688.934 | 61096.416 | 60079.328 | $100.00 | paper-graded (spot cannot short) |

## Accuracy so far

14 graded outcomes (5 win / 8 loss / 1 scratch) · win rate 38% · avg -0.05R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 3 new order(s), 10 symbols scanned

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
