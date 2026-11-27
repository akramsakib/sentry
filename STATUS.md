# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-27 23:30 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-226,101.72 · equity $100,632.00

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$395.66 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (0)

_None. Every symbol is scanned each cycle; a resting entry above is a trigger waiting to be hit, not a position._

## Positions (6)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BCH/USD | 49.2966 | 210.60611 | 206.69 | $-193.05 | 209.08471 | 212.88822 | -2.57R |
| DOGE/USD | 292204 | 0.05629 | 0.05754 | $365.25 | 0.05612059 | 0.056744 | +4.87R |
| ETH/USD | 9.00073 | 1689.5815 | 1657.75 | $-286.51 | 1678.4713 | 1706.2468 | -2.87R |
| LTC/USD | 203.958 | 44.260085 | 44.616 | $72.59 | 43.769787 | 44.995532 | +0.73R |
| SOL/USD | 89.9789 | 70.29 | 71.41 | $100.78 | 69.188628 | 71.689215 | +1.01R |
| XRP/USD | 5578.33 | 0.9326 | 0.9457 | $73.08 | 0.92035512 | 0.95060611 | +0.97R |

## Last 12 signals (848 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-27 23:30 | AVAX/USD | C-M15-gravestone | 4/5 | 6.5787805 | 6.6205488 | 6.5161281 | $100.00 | paper-graded (spot cannot short) |
| 11-27 23:30 | AVAX/USD | S13-ichimoku-short | 4/5 | 6.5746707 | 6.6621585 | 6.4471709 | $100.00 | paper-graded (spot cannot short) |
| 11-27 23:30 | BCH/USD | C-M15-evening-star | 3/5 | 205.79234 | 207.60416 | 203.07461 | $75.00 | not fired (guard/duplicate) |
| 11-27 23:30 | BCH/USD | C-M15-bear-engulfing | 3/5 | 205.79234 | 207.60416 | 203.07461 | $75.00 | not fired (guard/duplicate) |
| 11-27 23:30 | BCH/USD | C-M15-shooting-star | 3/5 | 205.79234 | 207.60416 | 203.07461 | $75.00 | not fired (guard/duplicate) |
| 11-27 23:30 | BCH/USD | C-H1-evening-star | 3/5 | 205.92234 | 207.80416 | 203.09961 | $75.00 | not fired (guard/duplicate) |
| 11-27 23:30 | BCH/USD | S13-ichimoku-short | 3/5 | 206.42351 | 211.48299 | 201.96143 | $75.00 | not fired (guard/duplicate) |
| 11-27 23:30 | BCH/USD | S18-rsi2-short | 4/5 | 206.75 | 209.36195 | 203.48506 | $100.00 | not fired (guard/duplicate) |
| 11-27 23:30 | LINK/USD | C-H1-three-outside-down | 4/5 | 9.3098758 | 9.4183105 | 9.1472237 | $100.00 | paper-graded (spot cannot short) |
| 11-27 23:30 | LINK/USD | C-H1-tweezer-top | 4/5 | 9.3098758 | 9.4183105 | 9.1472237 | $100.00 | paper-graded (spot cannot short) |
| 11-27 23:30 | LINK/USD | S18-rsi2-short | 4/5 | 9.339 | 9.4604905 | 9.1871368 | $100.00 | paper-graded (spot cannot short) |
| 11-27 23:30 | ADA/USD | S13-ichimoku-short | 4/5 | 0.14746215 | 0.15007571 | 0.14421147 | $100.00 | paper-graded (spot cannot short) |

## Accuracy so far

14 graded outcomes (5 win / 8 loss / 1 scratch) · win rate 38% · avg -0.05R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

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
