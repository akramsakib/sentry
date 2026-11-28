# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-28 04:56 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-208,786.09 · equity $100,690.07

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$396.66 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (1)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BCH/USD | buy_stop | 210.20338 | 61.1331 | $12,850 | $75.00 | 208.78 | +0.68% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (5)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| DOGE/USD | 292204 | 0.05629 | 0.0573 | $295.13 | 0.05612059 | 0.056744 | +3.94R |
| ETH/USD | 9.00073 | 1689.5815 | 1661.11 | $-256.26 | 1678.4713 | 1706.2468 | -2.56R |
| LTC/USD | 203.958 | 44.260085 | 44.503 | $49.54 | 43.769787 | 44.995532 | +0.50R |
| SOL/USD | 89.9789 | 70.29 | 71.52 | $110.67 | 69.188628 | 71.689215 | +1.11R |
| XRP/USD | 5578.33 | 0.9326 | 0.9477 | $84.23 | 0.92035512 | 0.95060611 | +1.12R |

## Last 12 signals (877 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-28 04:56 | AVAX/USD | C-M15-gravestone | 3/5 | 6.6014114 | 6.6329715 | 6.5540711 | $75.00 | paper-graded (spot cannot short) |
| 11-28 04:56 | AVAX/USD | C-H1-three-outside-down | 5/5 | 6.5944114 | 6.6609716 | 6.4945711 | $125.00 | paper-graded (spot cannot short) |
| 11-28 04:56 | AVAX/USD | C-H1-tweezer-top | 5/5 | 6.5944114 | 6.6609716 | 6.4945711 | $125.00 | paper-graded (spot cannot short) |
| 11-28 04:56 | AVAX/USD | S13-ichimoku-short | 4/5 | 6.5786171 | 6.6602659 | 6.4640504 | $100.00 | paper-graded (spot cannot short) |
| 11-28 04:56 | BCH/USD | C-M15-bull-engulfing | 3/5 | 210.20338 | 208.97655 | 212.04363 | $75.00 | order placed |
| 11-28 04:56 | LTC/USD | C-M15-bear-harami | 4/5 | 44.555067 | 44.872331 | 44.079172 | $100.00 | not fired (guard/duplicate) |
| 11-28 04:56 | LTC/USD | C-M15-tweezer-top | 4/5 | 44.555067 | 44.872331 | 44.079172 | $100.00 | not fired (guard/duplicate) |
| 11-28 04:56 | LTC/USD | C-H1-shooting-star | 4/5 | 44.675067 | 45.132331 | 43.989172 | $100.00 | not fired (guard/duplicate) |
| 11-28 04:56 | LTC/USD | S13-ichimoku-long | 3/5 | 44.567399 | 44.135203 | 45.488515 | $75.00 | not fired (guard/duplicate) |
| 11-28 04:56 | LTC/USD | S18-rsi2-long | 4/5 | 44.5 | 43.96081 | 45.173987 | $100.00 | not fired (guard/duplicate) |
| 11-28 04:56 | LINK/USD | C-M15-tweezer-top | 3/5 | 9.220779 | 9.2760525 | 9.1378688 | $75.00 | paper-graded (spot cannot short) |
| 11-28 04:56 | LINK/USD | C-H1-three-inside-down | 4/5 | 9.289779 | 9.4090525 | 9.1108688 | $100.00 | paper-graded (spot cannot short) |

## Accuracy so far

15 graded outcomes (5 win / 9 loss / 1 scratch) · win rate 36% · avg -0.23R · sizing today: score 3 -> $50.00 · score 4 -> $50.00 · score 5 -> $62.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 1 new order(s), 10 symbols scanned

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
