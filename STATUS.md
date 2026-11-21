# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-21 17:47 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-4,525.84 · equity $97,053.40

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$238.86 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (6)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| ADA/USD | buy_stop | 0.14558538 | 12084.8 | $1,759 | $75.00 | 0.1452 | +0.27% | 0 min |
| BTC/USD | buy_stop | 60242.79 | 0.0395638 | $2,383 | $75.00 | 60102.6 | +0.23% | 0 min |
| ETH/USD | buy_stop | 1684.7006 | 1.63393 | $2,753 | $75.00 | 1680.31 | +0.26% | 0 min |
| LINK/USD | buy_stop | 8.6178878 | 948.08 | $8,170 | $75.00 | 8.589 | +0.34% | 0 min |
| SOL/USD | buy_stop | 70.838406 | 25.3788 | $1,798 | $75.00 | 70.66 | +0.25% | 0 min |
| XRP/USD | buy_stop | 0.93675853 | 2129.13 | $1,994 | $75.00 | 0.9345 | +0.24% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (567 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-21 17:47 | LINK/USD | C-M15-tweezer-bottom | 3/5 | 8.6178878 | 8.5387805 | 8.7365487 | $75.00 | order placed |
| 11-21 17:47 | ADA/USD | S13-ichimoku-long | 3/5 | 0.14558538 | 0.13937925 | 0.15085217 | $75.00 | order placed |
| 11-21 17:47 | SOL/USD | S13-ichimoku-long | 3/5 | 70.838406 | 67.883187 | 73.276628 | $75.00 | order placed |
| 11-21 17:47 | XRP/USD | S21-pivot-S1-short | 4/5 | 0.94792765 | 0.97336667 | 0.90156667 | $100.00 | paper-graded (spot cannot short) |
| 11-21 17:47 | XRP/USD | S13-ichimoku-long | 3/5 | 0.93675853 | 0.90153294 | 0.9676251 | $75.00 | order placed |
| 11-21 17:47 | ETH/USD | S13-ichimoku-long | 3/5 | 1684.7006 | 1638.7989 | 1744.7048 | $75.00 | order placed |
| 11-21 17:47 | BTC/USD | S13-ichimoku-long | 3/5 | 60242.79 | 58347.119 | 62158.727 | $75.00 | order placed |
| 11-21 10:45 | BCH/USD | S13-ichimoku-short | 4/5 | 189.13245 | 193.6401 | 180.96592 | $100.00 | paper-graded (spot cannot short) |
| 11-21 10:45 | LTC/USD | S13-ichimoku-short | 4/5 | 38.493367 | 39.918266 | 37.036048 | $100.00 | paper-graded (spot cannot short) |
| 11-21 10:45 | ADA/USD | S13-ichimoku-short | 4/5 | 0.13897728 | 0.14264543 | 0.13320015 | $100.00 | paper-graded (spot cannot short) |
| 11-21 10:45 | ADA/USD | S1-pullback-short | 4/5 | 0.14080581 | 0.14170453 | 0.13945774 | $100.00 | paper-graded (spot cannot short) |
| 11-21 10:45 | DOGE/USD | S13-ichimoku-short | 4/5 | 0.05290509 | 0.05453481 | 0.05078803 | $100.00 | paper-graded (spot cannot short) |

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
