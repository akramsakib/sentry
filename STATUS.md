# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-15 00:24 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $95,406.85 · equity $99,833.68

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$62.57 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (5)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| ETH/USD | buy_stop | 1841.7081 | 2.63387 | $4,851 | $50.00 | 1771.27 | +3.98% | 255 min |
| ETH/USD | buy_stop | 1841.7081 | 2.63387 | $4,851 | $50.00 | 1771.27 | +3.98% | 255 min |
| LINK/USD | buy_stop | 8.8743714 | 274.274 | $2,434 | $50.00 | 8.902 | -0.31% | 122 min |
| SOL/USD | buy_stop | 72.591023 | 59.2712 | $4,303 | $50.00 | 70.44 | +3.05% | 255 min |
| XRP/USD | buy_stop | 0.9568033 | 5548.44 | $5,309 | $50.00 | 0.9277 | +3.14% | 255 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (1)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BTC/USD | 0.069084 | 63278.87 | 64078.8 | $55.26 | 63069.244 | 66371.462 | +1.11R |

## Last 12 signals (100 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-15 00:24 | AVAX/USD | S13-ichimoku-short | 4/5 | 7.0890152 | 7.6999696 | 6.7885559 | $50.00 | paper-graded (spot cannot short) |
| 11-15 00:24 | BCH/USD | S13-ichimoku-short | 4/5 | 201.46582 | 212.31835 | 193.34542 | $50.00 | paper-graded (spot cannot short) |
| 11-15 00:24 | LTC/USD | S3-momentum-short | 4/5 | 43.302236 | 44.465529 | 41.053414 | $50.00 | paper-graded (spot cannot short) |
| 11-15 00:24 | LTC/USD | S13-ichimoku-short | 4/5 | 44.543354 | 46.778293 | 42.949186 | $50.00 | paper-graded (spot cannot short) |
| 11-15 00:24 | ADA/USD | S3-momentum-short | 4/5 | 0.14269358 | 0.14791284 | 0.13256147 | $50.00 | paper-graded (spot cannot short) |
| 11-15 00:24 | ADA/USD | S13-ichimoku-short | 4/5 | 0.14794037 | 0.15776926 | 0.14165873 | $50.00 | paper-graded (spot cannot short) |
| 11-15 00:24 | DOGE/USD | S13-ichimoku-short | 4/5 | 0.05752469 | 0.06071063 | 0.05512873 | $50.00 | paper-graded (spot cannot short) |
| 11-15 00:24 | BTC/USD | C-M15-three-inside-up | 3/5 | 64259.844 | 63392.24 | 65561.249 | $50.00 | not fired (guard/duplicate) |
| 11-15 00:24 | BTC/USD | C-M15-bull-engulfing | 3/5 | 64259.844 | 63392.24 | 65561.249 | $50.00 | not fired (guard/duplicate) |
| 11-15 00:24 | BTC/USD | C-M15-marubozu | 3/5 | 64259.844 | 63392.24 | 65561.249 | $50.00 | not fired (guard/duplicate) |
| 11-15 00:24 | BTC/USD | S13-ichimoku-short | 4/5 | 64156.784 | 66308.981 | 62591.736 | $50.00 | not fired (guard/duplicate) |
| 11-15 00:24 | BTC/USD | S11-dc55-short | 4/5 | 63780.156 | 64314.563 | 62176.936 | $50.00 | not fired (guard/duplicate) |

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
