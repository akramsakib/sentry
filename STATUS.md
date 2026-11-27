# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-27 15:12 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-243,931.53 · equity $98,353.87

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$386.99 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (0)

_None. Every symbol is scanned each cycle; a resting entry above is a trigger waiting to be hit, not a position._

## Positions (6)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BCH/USD | 49.2966 | 210.60611 | 203.74 | $-338.48 | 209.08471 | 212.88822 | -4.51R |
| DOGE/USD | 292204 | 0.05629 | 0.05699 | $204.54 | 0.05612059 | 0.056744 | +2.73R |
| ETH/USD | 9.00073 | 1689.5815 | 1653.62 | $-323.68 | 1678.4713 | 1706.2468 | -3.24R |
| LTC/USD | 203.958 | 44.260085 | 43.463 | $-162.57 | 43.769787 | 44.995532 | -1.63R |
| SOL/USD | 89.9789 | 70.29 | 71.26 | $87.28 | 69.188628 | 71.689215 | +0.87R |
| XRP/USD | 5578.33 | 0.9326 | 0.9419 | $51.88 | 0.92035512 | 0.95060611 | +0.69R |

## Last 12 signals (829 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-27 15:12 | BCH/USD | C-H1-tweezer-bottom | 3/5 | 212.22522 | 209.62696 | 216.12261 | $75.00 | not fired (guard/duplicate) |
| 11-27 15:12 | BCH/USD | C-H1-bull-engulfing | 3/5 | 212.22522 | 209.62696 | 216.12261 | $75.00 | not fired (guard/duplicate) |
| 11-27 15:12 | BCH/USD | S18-ma-revert-long | 3/5 | 202.24 | 199.78782 | 210.71319 | $75.00 | not fired (guard/duplicate) |
| 11-27 15:12 | BCH/USD | S4-band-fade-long | 4/5 | 206.27456 | 200.76869 | 211.7785 | $100.00 | not fired (guard/duplicate) |
| 11-27 15:12 | LTC/USD | C-H1-three-outside-down | 4/5 | 44.337403 | 44.816491 | 43.618771 | $100.00 | not fired (guard/duplicate) |
| 11-27 15:12 | LTC/USD | C-H1-tweezer-top | 4/5 | 44.337403 | 44.816491 | 43.618771 | $100.00 | not fired (guard/duplicate) |
| 11-27 15:12 | LTC/USD | C-H1-bear-engulfing | 4/5 | 44.337403 | 44.816491 | 43.618771 | $100.00 | not fired (guard/duplicate) |
| 11-27 15:12 | LTC/USD | C-H1-marubozu | 4/5 | 44.337403 | 44.816491 | 43.618771 | $100.00 | not fired (guard/duplicate) |
| 11-27 15:12 | LTC/USD | S4-band-fade-long | 4/5 | 43.501527 | 42.954421 | 44.254 | $100.00 | not fired (guard/duplicate) |
| 11-27 15:12 | DOGE/USD | C-H1-three-outside-up | 3/5 | 0.05910145 | 0.05834638 | 0.06023405 | $75.00 | not fired (guard/duplicate) |
| 11-27 15:12 | DOGE/USD | C-H1-tweezer-bottom | 3/5 | 0.05910145 | 0.05834638 | 0.06023405 | $75.00 | not fired (guard/duplicate) |
| 11-27 15:12 | XRP/USD | C-H1-marubozu | 4/5 | 0.96683325 | 0.97611687 | 0.95290782 | $100.00 | not fired (guard/duplicate) |

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
