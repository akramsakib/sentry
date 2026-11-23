# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-23 13:43 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-100,528.14 · equity $100,605.30

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$286.83 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (6)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_stop | 61326.149 | 0.222852 | $13,667 | $75.00 | 61311.9 | +0.02% | 0 min |
| DOGE/USD | buy_stop | 0.05567813 | 112044 | $6,238 | $75.00 | 0.05571 | -0.06% | 0 min |
| ETH/USD | buy_stop | 1726.1756 | 4.23978 | $7,319 | $75.00 | 1725.22 | +0.06% | 0 min |
| SOL/USD | buy_stop | 72.555231 | 113.928 | $8,266 | $75.00 | 72.59 | -0.05% | 0 min |
| XRP/USD | buy_stop | 0.94157069 | 5132.75 | $4,833 | $75.00 | 0.9424 | -0.09% | 0 min |
| XRP/USD | buy_stop | 0.94468046 | 6618.66 | $6,253 | $75.00 | 0.9424 | +0.24% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (638 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-23 13:43 | DOGE/USD | S13-ichimoku-long | 3/5 | 0.05567813 | 0.05500875 | 0.05660919 | $75.00 | order placed |
| 11-23 13:43 | SOL/USD | C-M15-morning-star | 3/5 | 72.555231 | 71.896921 | 73.542697 | $75.00 | order placed |
| 11-23 13:43 | XRP/USD | S22-rsi-bull-div | 3/5 | 0.94468046 | 0.93334886 | 0.96167786 | $75.00 | order placed |
| 11-23 13:43 | XRP/USD | S13-ichimoku-long | 3/5 | 0.94157069 | 0.92695863 | 0.95757006 | $75.00 | order placed |
| 11-23 13:43 | ETH/USD | S22-rsi-bull-div | 3/5 | 1726.1756 | 1708.486 | 1752.71 | $75.00 | order placed |
| 11-23 13:43 | BTC/USD | C-M15-bear-harami | 4/5 | 61139.434 | 61501.015 | 60597.064 | $100.00 | paper-graded (spot cannot short) |
| 11-23 13:43 | BTC/USD | S13-ichimoku-long | 3/5 | 61326.149 | 60989.603 | 62362.748 | $75.00 | order placed |
| 11-23 03:42 | AVAX/USD | C-H1-marubozu | 5/5 | 6.5943514 | 6.6731215 | 6.4761963 | $125.00 | paper-graded (spot cannot short) |
| 11-23 03:42 | BCH/USD | C-H1-marubozu | 5/5 | 196.68612 | 199.02969 | 193.17077 | $125.00 | paper-graded (spot cannot short) |
| 11-23 03:42 | LINK/USD | C-H1-tweezer-top | 5/5 | 8.7748513 | 8.8628717 | 8.6428208 | $125.00 | paper-graded (spot cannot short) |
| 11-23 03:42 | LINK/USD | C-H1-bear-engulfing | 5/5 | 8.7748513 | 8.8628717 | 8.6428208 | $125.00 | paper-graded (spot cannot short) |
| 11-23 03:42 | DOGE/USD | C-M15-marubozu | 4/5 | 0.05516596 | 0.0544151 | 0.05629225 | $100.00 | order placed |

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
