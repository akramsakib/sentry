# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-14 23:49 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $95,406.85 · equity $99,827.22

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$62.57 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (5)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| ETH/USD | buy_stop | 1841.7081 | 2.63387 | $4,851 | $50.00 | 1750.19 | +5.23% | 219 min |
| ETH/USD | buy_stop | 1841.7081 | 2.63387 | $4,851 | $50.00 | 1750.19 | +5.23% | 219 min |
| LINK/USD | buy_stop | 8.8743714 | 274.274 | $2,434 | $50.00 | 8.772 | +1.17% | 87 min |
| SOL/USD | buy_stop | 72.591023 | 59.2712 | $4,303 | $50.00 | 69.42 | +4.57% | 219 min |
| XRP/USD | buy_stop | 0.9568033 | 5548.44 | $5,309 | $50.00 | 0.9014 | +6.15% | 219 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (1)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BTC/USD | 0.069084 | 63278.87 | 63985.4 | $48.81 | 63069.244 | 66371.462 | +0.98R |

## Last 12 signals (85 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-14 23:22 | DOGE/USD | S18-rsi2-short | 3/5 | 0.05652 | 0.05790025 | 0.05479469 | $50.00 | paper-graded (spot cannot short) |
| 11-14 23:18 | ADA/USD | S18-rsi2-short | 3/5 | 0.1455 | 0.14911837 | 0.14097704 | $50.00 | paper-graded (spot cannot short) |
| 11-14 23:01 | AVAX/USD | S16-inside-short | 4/5 | 6.9531776 | 7.1510561 | 6.7456634 | $50.00 | paper-graded (spot cannot short) |
| 11-14 23:01 | BCH/USD | S16-inside-short | 4/5 | 197.3421 | 202.20974 | 191.91157 | $50.00 | paper-graded (spot cannot short) |
| 11-14 23:01 | ADA/USD | S16-inside-short | 4/5 | 0.14349847 | 0.14765383 | 0.13927704 | $50.00 | paper-graded (spot cannot short) |
| 11-14 23:01 | DOGE/USD | S16-inside-short | 4/5 | 0.05553498 | 0.05707755 | 0.05392469 | $50.00 | paper-graded (spot cannot short) |
| 11-14 23:01 | BTC/USD | S16-inside-short | 4/5 | 63274.08 | 64485.649 | 62218.207 | $50.00 | not fired (guard/duplicate) |
| 11-14 23:01 | BTC/USD | S16-inside-long | 3/5 | 64372.52 | 63160.951 | 65428.393 | $50.00 | not fired (guard/duplicate) |
| 11-14 22:22 | AVAX/USD | C-M15-evening-star | 4/5 | 7.0514681 | 7.1953296 | 6.8356759 | $50.00 | paper-graded (spot cannot short) |
| 11-14 22:22 | LTC/USD | S16-inside-short | 4/5 | 43.993676 | 44.900811 | 42.925137 | $50.00 | paper-graded (spot cannot short) |
| 11-14 22:22 | LINK/USD | C-M15-bear-engulfing | 3/5 | 8.7186286 | 8.8679284 | 8.4946791 | $50.00 | paper-graded (spot cannot short) |
| 11-14 22:22 | LINK/USD | S16-inside-short | 4/5 | 8.7166287 | 8.8989284 | 8.4874297 | $50.00 | paper-graded (spot cannot short) |

## Accuracy so far

1 graded outcomes (0 win / 1 loss) · win rate 0% · avg -0.61R · sizing today: score 3 -> $50.00 · score 4 -> $50.00 · score 5 -> $62.00

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
