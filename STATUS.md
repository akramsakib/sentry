# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-25 14:15 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-152,586.33 · equity $87,687.75

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$312.85 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (6)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_stop | 58819.192 | 0.143494 | $8,440 | $75.00 | 58051.1 | +1.32% | 0 min |
| BTC/USD | buy_stop | 58819.192 | 0.143494 | $8,440 | $75.00 | 58051.1 | +1.32% | 0 min |
| DOGE/USD | buy_limit | 0.05294 | 217757 | $11,528 | $75.00 | 0.05288 | +0.11% | 0 min |
| ETH/USD | buy_stop | 1650.4085 | 5.19357 | $8,572 | $100.00 | 1631.31 | +1.17% | 0 min |
| SOL/USD | buy_limit | 66.91 | 155.777 | $10,423 | $75.00 | 66.82 | +0.13% | 0 min |
| XRP/USD | buy_limit | 0.8959 | 12864.5 | $11,525 | $75.00 | 0.8941 | +0.20% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (724 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-25 14:15 | BCH/USD | C-M15-three-inside-down | 5/5 | 192.00887 | 196.12282 | 185.83794 | $125.00 | paper-graded (spot cannot short) |
| 11-25 14:15 | BCH/USD | C-M15-tweezer-top | 5/5 | 192.00887 | 196.12282 | 185.83794 | $125.00 | paper-graded (spot cannot short) |
| 11-25 14:15 | BCH/USD | S21-pivot-S1-short | 4/5 | 194.2622 | 197.50667 | 188.43667 | $100.00 | paper-graded (spot cannot short) |
| 11-25 14:15 | BCH/USD | S13-ichimoku-short | 4/5 | 193.03831 | 197.32839 | 188.50516 | $100.00 | paper-graded (spot cannot short) |
| 11-25 14:15 | LTC/USD | C-M15-three-outside-down | 5/5 | 39.715824 | 40.350439 | 38.763903 | $125.00 | paper-graded (spot cannot short) |
| 11-25 14:15 | LTC/USD | C-M15-tweezer-top | 5/5 | 39.715824 | 40.350439 | 38.763903 | $125.00 | paper-graded (spot cannot short) |
| 11-25 14:15 | LINK/USD | C-M15-three-outside-down | 4/5 | 8.5375211 | 8.6956973 | 8.3002568 | $100.00 | paper-graded (spot cannot short) |
| 11-25 14:15 | LINK/USD | C-M15-tweezer-top | 4/5 | 8.5375211 | 8.6956973 | 8.3002568 | $100.00 | paper-graded (spot cannot short) |
| 11-25 14:15 | LINK/USD | S21-pivot-S1-short | 4/5 | 8.5521878 | 8.7333333 | 8.2183333 | $100.00 | paper-graded (spot cannot short) |
| 11-25 14:15 | ADA/USD | C-M15-three-outside-down | 4/5 | 0.13742649 | 0.13993377 | 0.13366559 | $100.00 | paper-graded (spot cannot short) |
| 11-25 14:15 | ADA/USD | C-M15-tweezer-top | 4/5 | 0.13742649 | 0.13993377 | 0.13366559 | $100.00 | paper-graded (spot cannot short) |
| 11-25 14:15 | DOGE/USD | C-M15-three-outside-down | 4/5 | 0.0527726 | 0.05387351 | 0.05112122 | $100.00 | paper-graded (spot cannot short) |

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
