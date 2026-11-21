# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-21 10:45 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $32,951.53 · equity $93,855.08

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$220.13 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (6)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_stop | 58293.457 | 0.112926 | $6,583 | $75.00 | 57858.2 | +0.75% | 0 min |
| ETH/USD | buy_stop | 1650.5624 | 4.30413 | $7,104 | $100.00 | 1639.48 | +0.68% | 0 min |
| ETH/USD | buy_stop | 1650.5624 | 4.30413 | $7,104 | $100.00 | 1639.48 | +0.68% | 0 min |
| SOL/USD | buy_stop | 68.50878 | 83.2657 | $5,704 | $75.00 | 68.08 | +0.63% | 0 min |
| SOL/USD | buy_stop | 68.50878 | 83.2657 | $5,704 | $75.00 | 68.08 | +0.63% | 0 min |
| XRP/USD | buy_stop | 0.8990781 | 5848.7 | $5,258 | $75.00 | 0.8952 | +0.43% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (560 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-21 10:45 | BCH/USD | S13-ichimoku-short | 4/5 | 189.13245 | 193.6401 | 180.96592 | $100.00 | paper-graded (spot cannot short) |
| 11-21 10:45 | LTC/USD | S13-ichimoku-short | 4/5 | 38.493367 | 39.918266 | 37.036048 | $100.00 | paper-graded (spot cannot short) |
| 11-21 10:45 | ADA/USD | S13-ichimoku-short | 4/5 | 0.13897728 | 0.14264543 | 0.13320015 | $100.00 | paper-graded (spot cannot short) |
| 11-21 10:45 | ADA/USD | S1-pullback-short | 4/5 | 0.14080581 | 0.14170453 | 0.13945774 | $100.00 | paper-graded (spot cannot short) |
| 11-21 10:45 | DOGE/USD | S13-ichimoku-short | 4/5 | 0.05290509 | 0.05453481 | 0.05078803 | $100.00 | paper-graded (spot cannot short) |
| 11-21 10:45 | DOGE/USD | S1-pullback-short | 4/5 | 0.05384131 | 0.05408818 | 0.053471 | $100.00 | paper-graded (spot cannot short) |
| 11-21 10:45 | SOL/USD | C-M15-three-inside-up | 3/5 | 68.50878 | 67.608049 | 69.859877 | $75.00 | order placed |
| 11-21 10:45 | SOL/USD | C-M15-tweezer-bottom | 3/5 | 68.50878 | 67.608049 | 69.859877 | $75.00 | order placed |
| 11-21 10:45 | XRP/USD | C-M15-tweezer-bottom | 3/5 | 0.8990781 | 0.88625474 | 0.91831315 | $75.00 | order placed |
| 11-21 10:45 | XRP/USD | S13-ichimoku-short | 4/5 | 0.89283284 | 0.92043431 | 0.8604817 | $100.00 | paper-graded (spot cannot short) |
| 11-21 10:45 | XRP/USD | S1-pullback-short | 3/5 | 0.90426658 | 0.90724526 | 0.89979857 | $75.00 | paper-graded (spot cannot short) |
| 11-21 10:45 | ETH/USD | C-M15-three-inside-up | 4/5 | 1650.5624 | 1627.3289 | 1685.4127 | $100.00 | order placed |

## Accuracy so far

14 graded outcomes (5 win / 8 loss / 1 scratch) · win rate 38% · avg -0.05R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 6 new order(s), 10 symbols scanned

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
