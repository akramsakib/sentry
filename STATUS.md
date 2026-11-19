# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-19 23:54 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $38,112.89 · equity $98,371.79

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$199.25 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (0)

_None. Every symbol is scanned each cycle; a resting entry above is a trigger waiting to be hit, not a position._

## Positions (2)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| SOL/USD | 108.486 | 72.53 | 73.08 | $59.67 | 72.273804 | 74.428 | +1.07R |
| XRP/USD | 4643.61 | 0.95972892 | 0.9598 | $0.33 | 0.94357771 | 0.97833374 | +0.00R |

## Last 12 signals (473 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-19 23:54 | AVAX/USD | S11-dc20-short | 4/5 | 6.8948335 | 6.958999 | 6.7023369 | $50.00 | paper-graded (spot cannot short) |
| 11-19 23:54 | BCH/USD | C-H1-marubozu | 5/5 | 203.21017 | 207.42957 | 196.88108 | $62.00 | paper-graded (spot cannot short) |
| 11-19 23:54 | BCH/USD | S11-dc20-short | 4/5 | 203.60017 | 205.27897 | 198.56379 | $50.00 | paper-graded (spot cannot short) |
| 11-19 23:54 | LTC/USD | S13-ichimoku-short | 4/5 | 42.167948 | 43.349103 | 41.183243 | $50.00 | paper-graded (spot cannot short) |
| 11-19 23:54 | LTC/USD | S11-dc55-short | 4/5 | 42.071966 | 42.408207 | 41.063243 | $50.00 | paper-graded (spot cannot short) |
| 11-19 23:54 | LTC/USD | S11-dc20-short | 4/5 | 42.071966 | 42.408207 | 41.063243 | $50.00 | paper-graded (spot cannot short) |
| 11-19 23:54 | LINK/USD | S11-dc55-short | 4/5 | 8.870046 | 8.9467237 | 8.6400131 | $50.00 | paper-graded (spot cannot short) |
| 11-19 23:54 | LINK/USD | S11-dc20-short | 4/5 | 8.9030461 | 8.9797237 | 8.673013 | $50.00 | paper-graded (spot cannot short) |
| 11-19 23:54 | ADA/USD | C-H1-three-crows | 5/5 | 0.14951522 | 0.15216196 | 0.14554509 | $62.00 | paper-graded (spot cannot short) |
| 11-19 23:54 | DOGE/USD | C-H1-three-crows | 5/5 | 0.05735395 | 0.05840512 | 0.05577721 | $62.00 | paper-graded (spot cannot short) |
| 11-19 23:54 | DOGE/USD | S13-ichimoku-short | 4/5 | 0.05801093 | 0.05882814 | 0.05665697 | $50.00 | paper-graded (spot cannot short) |
| 11-19 23:54 | DOGE/USD | S11-dc20-short | 4/5 | 0.05784395 | 0.05830628 | 0.05645697 | $50.00 | paper-graded (spot cannot short) |

## Accuracy so far

12 graded outcomes (3 win / 8 loss / 1 scratch) · win rate 27% · avg -0.16R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

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
