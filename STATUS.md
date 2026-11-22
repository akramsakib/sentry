# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-22 02:32 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-4,525.84 · equity $96,460.34

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$250.22 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (6)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_limit | 59821.1 | 0.135056 | $8,079 | $100.00 | 59821.1 | +0.00% | 0 min |
| BTC/USD | buy_stop | 59913.654 | 0.0363414 | $2,177 | $75.00 | 59821.1 | +0.15% | 0 min |
| DOGE/USD | buy_stop | 0.05505256 | 36806.6 | $2,026 | $75.00 | 0.05496 | +0.17% | 0 min |
| ETH/USD | buy_stop | 1682.4062 | 1.21127 | $2,038 | $75.00 | 1679.58 | +0.17% | 0 min |
| SOL/USD | buy_limit | 70.04 | 106.507 | $7,460 | $100.00 | 70.04 | +0.00% | 0 min |
| XRP/USD | buy_limit | 0.9281 | 7825 | $7,262 | $100.00 | 0.9281 | +0.00% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (596 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-22 02:32 | AVAX/USD | C-H1-bear-harami | 3/5 | 6.5526053 | 6.6039867 | 6.4755333 | $75.00 | paper-graded (spot cannot short) |
| 11-22 02:32 | BCH/USD | C-H1-bear-harami | 4/5 | 198.86598 | 200.97006 | 195.70986 | $100.00 | paper-graded (spot cannot short) |
| 11-22 02:32 | BCH/USD | S21-pivot-S1-short | 4/5 | 201.45264 | 206.20333 | 192.68333 | $100.00 | paper-graded (spot cannot short) |
| 11-22 02:32 | LTC/USD | C-H1-bear-harami | 3/5 | 39.612828 | 39.897929 | 39.185177 | $75.00 | paper-graded (spot cannot short) |
| 11-22 02:32 | LINK/USD | C-M15-evening-star | 4/5 | 8.5652285 | 8.6194287 | 8.4839283 | $100.00 | paper-graded (spot cannot short) |
| 11-22 02:32 | LINK/USD | C-H1-bear-harami | 4/5 | 8.5792285 | 8.6374287 | 8.4919283 | $100.00 | paper-graded (spot cannot short) |
| 11-22 02:32 | LINK/USD | C-H1-tweezer-top | 4/5 | 8.5792285 | 8.6374287 | 8.4919283 | $100.00 | paper-graded (spot cannot short) |
| 11-22 02:32 | LINK/USD | S22-rsi-bear-div | 4/5 | 8.5652285 | 8.6404287 | 8.4524283 | $100.00 | paper-graded (spot cannot short) |
| 11-22 02:32 | ADA/USD | C-H1-bear-harami | 4/5 | 0.14382367 | 0.14504081 | 0.14199797 | $100.00 | paper-graded (spot cannot short) |
| 11-22 02:32 | ADA/USD | C-H1-tweezer-top | 4/5 | 0.14382367 | 0.14504081 | 0.14199797 | $100.00 | paper-graded (spot cannot short) |
| 11-22 02:32 | DOGE/USD | C-M15-evening-star | 4/5 | 0.05497829 | 0.05535427 | 0.05441433 | $100.00 | paper-graded (spot cannot short) |
| 11-22 02:32 | DOGE/USD | S22-rsi-bear-div | 4/5 | 0.05497829 | 0.05544427 | 0.05427933 | $100.00 | paper-graded (spot cannot short) |

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
