# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-27 05:15 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-263,508.44 · equity $109,110.58

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$368.28 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (0)

_None. Every symbol is scanned each cycle; a resting entry above is a trigger waiting to be hit, not a position._

## Positions (6)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BCH/USD | 49.2966 | 210.60611 | 214.38 | $186.04 | 209.08471 | 212.88822 | +2.48R |
| DOGE/USD | 292204 | 0.05629 | 0.05774 | $423.70 | 0.05612059 | 0.056744 | +5.65R |
| ETH/USD | 9.00073 | 1689.5815 | 1738.96 | $444.44 | 1678.4713 | 1706.2468 | +4.44R |
| LTC/USD | 203.958 | 44.260085 | 44.622 | $73.82 | 43.769787 | 44.995532 | +0.74R |
| SOL/USD | 89.9789 | 70.29 | 72.93 | $237.54 | 69.188628 | 71.689215 | +2.38R |
| XRP/USD | 5578.33 | 0.9326 | 0.9618 | $162.89 | 0.92035512 | 0.95060611 | +2.17R |

## Last 12 signals (811 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-27 05:15 | AVAX/USD | S4-band-fade-short | 3/5 | 6.7275581 | 6.7901814 | 6.6402 | $75.00 | paper-graded (spot cannot short) |
| 11-27 05:15 | BCH/USD | C-H1-tweezer-top | 4/5 | 215.78955 | 219.90613 | 209.61468 | $100.00 | not fired (guard/duplicate) |
| 11-27 05:15 | BCH/USD | S13-ichimoku-long | 3/5 | 214.94568 | 211.34365 | 219.66992 | $75.00 | not fired (guard/duplicate) |
| 11-27 05:15 | LTC/USD | C-H1-shooting-star | 3/5 | 44.310414 | 44.728965 | 43.682586 | $75.00 | not fired (guard/duplicate) |
| 11-27 05:15 | LTC/USD | S13-ichimoku-long | 3/5 | 44.679379 | 43.691241 | 45.490896 | $75.00 | not fired (guard/duplicate) |
| 11-27 05:15 | LINK/USD | S18-ma-revert-short | 3/5 | 9.634 | 9.7332681 | 9.3145936 | $75.00 | paper-graded (spot cannot short) |
| 11-27 05:15 | LINK/USD | S4-band-fade-short | 4/5 | 9.5172127 | 9.6935609 | 9.29945 | $100.00 | paper-graded (spot cannot short) |
| 11-27 05:15 | DOGE/USD | C-M15-three-outside-down | 4/5 | 0.05758334 | 0.05790666 | 0.05709835 | $100.00 | not fired (guard/duplicate) |
| 11-27 05:15 | DOGE/USD | C-M15-bear-engulfing | 4/5 | 0.05758334 | 0.05790666 | 0.05709835 | $100.00 | not fired (guard/duplicate) |
| 11-27 05:15 | DOGE/USD | C-M15-marubozu | 4/5 | 0.05758334 | 0.05790666 | 0.05709835 | $100.00 | not fired (guard/duplicate) |
| 11-27 05:15 | DOGE/USD | S23-upthrust-short | 4/5 | 0.05741334 | 0.05813666 | 0.05630268 | $100.00 | not fired (guard/duplicate) |
| 11-27 05:15 | DOGE/USD | S22-rsi-bear-div | 4/5 | 0.05758334 | 0.05813666 | 0.05675335 | $100.00 | not fired (guard/duplicate) |

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
