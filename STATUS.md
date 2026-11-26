# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-26 04:59 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-204,798.74 · equity $102,831.02

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$341.91 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (3)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_limit | 60948.1 | 0.0974913 | $5,942 | $75.00 | 60981.6 | -0.05% | 0 min |
| BTC/USD | buy_stop | 61044.262 | 0.0417203 | $2,547 | $75.00 | 60981.6 | +0.10% | 0 min |
| ETH/USD | buy_limit | 1681.73 | 4.06209 | $6,831 | $100.00 | 1702.93 | -1.24% | 351 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (3)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| ETH/USD | 9.00073 | 1689.5815 | 1699.6 | $90.17 | 1678.4713 | 1706.2468 | +0.90R |
| SOL/USD | 89.9789 | 70.29 | 71 | $63.89 | 69.188628 | 71.689215 | +0.64R |
| XRP/USD | 5578.33 | 0.9326 | 0.9568 | $135.00 | 0.92035512 | 0.95060611 | +1.80R |

## Last 12 signals (753 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-26 04:59 | BCH/USD | C-M15-gravestone | 3/5 | 208.00581 | 209.55048 | 205.68881 | $75.00 | paper-graded (spot cannot short) |
| 11-26 04:59 | LTC/USD | S23-upthrust-short | 4/5 | 43.286533 | 44.043667 | 42.128585 | $100.00 | paper-graded (spot cannot short) |
| 11-26 04:59 | LTC/USD | S18-ma-revert-short | 3/5 | 43.8 | 44.334669 | 42.106997 | $75.00 | paper-graded (spot cannot short) |
| 11-26 04:59 | LINK/USD | C-H1-bear-harami | 4/5 | 9.1185579 | 9.2706054 | 8.8904866 | $100.00 | paper-graded (spot cannot short) |
| 11-26 04:59 | ADA/USD | S23-upthrust-short | 4/5 | 0.14710267 | 0.14949333 | 0.14347494 | $100.00 | paper-graded (spot cannot short) |
| 11-26 04:59 | SOL/USD | C-M15-tweezer-top | 4/5 | 71.045266 | 71.471834 | 70.405414 | $100.00 | not fired (guard/duplicate) |
| 11-26 04:59 | SOL/USD | S13-ichimoku-long | 3/5 | 71.247101 | 68.585799 | 72.984142 | $75.00 | not fired (guard/duplicate) |
| 11-26 04:59 | XRP/USD | C-M15-bear-harami | 4/5 | 0.9560075 | 0.96343124 | 0.94487189 | $100.00 | not fired (guard/duplicate) |
| 11-26 04:59 | XRP/USD | C-M15-tweezer-top | 4/5 | 0.9560075 | 0.96343124 | 0.94487189 | $100.00 | not fired (guard/duplicate) |
| 11-26 04:59 | XRP/USD | C-M15-marubozu | 4/5 | 0.9560075 | 0.96343124 | 0.94487189 | $100.00 | not fired (guard/duplicate) |
| 11-26 04:59 | XRP/USD | S13-ichimoku-long | 3/5 | 0.96043875 | 0.92107251 | 0.98283493 | $75.00 | not fired (guard/duplicate) |
| 11-26 04:59 | BTC/USD | S13-ichimoku-long | 3/5 | 61044.262 | 59246.575 | 62358.483 | $75.00 | order placed |

## Accuracy so far

14 graded outcomes (5 win / 8 loss / 1 scratch) · win rate 38% · avg -0.05R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 2 new order(s), 10 symbols scanned

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
