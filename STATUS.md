# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-25 04:08 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-152,586.33 · equity $92,583.04

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$312.85 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (6)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_stop | 59393.651 | 0.121285 | $7,204 | $75.00 | 59391.2 | +0.00% | 0 min |
| DOGE/USD | buy_stop | 0.05476678 | 134233 | $7,352 | $75.00 | 0.05461 | +0.29% | 0 min |
| ETH/USD | buy_stop | 1668.7326 | 2.9971 | $5,001 | $75.00 | 1663.67 | +0.30% | 0 min |
| ETH/USD | buy_stop | 1668.7326 | 6.3003 | $10,514 | $75.00 | 1663.67 | +0.30% | 0 min |
| SOL/USD | buy_stop | 69.49126 | 150.51 | $10,459 | $100.00 | 69.3 | +0.28% | 0 min |
| XRP/USD | buy_stop | 0.91964732 | 6569.95 | $6,042 | $75.00 | 0.9204 | -0.08% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (700 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-25 04:08 | AVAX/USD | S13-ichimoku-short | 4/5 | 6.4998877 | 6.6827245 | 6.34802 | $100.00 | paper-graded (spot cannot short) |
| 11-25 04:08 | BCH/USD | C-M15-evening-star | 4/5 | 195.96677 | 197.51306 | 193.64734 | $100.00 | paper-graded (spot cannot short) |
| 11-25 04:08 | LTC/USD | S13-ichimoku-short | 4/5 | 40.383086 | 41.083828 | 39.468595 | $100.00 | paper-graded (spot cannot short) |
| 11-25 04:08 | LINK/USD | S13-ichimoku-short | 4/5 | 8.7518126 | 8.9558748 | 8.5579184 | $100.00 | paper-graded (spot cannot short) |
| 11-25 04:08 | ADA/USD | C-M15-shooting-star | 4/5 | 0.14263291 | 0.14381772 | 0.14085569 | $100.00 | paper-graded (spot cannot short) |
| 11-25 04:08 | ADA/USD | S13-ichimoku-short | 4/5 | 0.14234937 | 0.14660127 | 0.13892404 | $100.00 | paper-graded (spot cannot short) |
| 11-25 04:08 | DOGE/USD | C-M15-evening-star | 4/5 | 0.05458322 | 0.05500195 | 0.05395513 | $100.00 | paper-graded (spot cannot short) |
| 11-25 04:08 | DOGE/USD | S23-spring-long | 3/5 | 0.05476678 | 0.05420805 | 0.05560396 | $75.00 | order placed |
| 11-25 04:08 | DOGE/USD | S13-ichimoku-short | 4/5 | 0.05436483 | 0.05592534 | 0.05320085 | $100.00 | paper-graded (spot cannot short) |
| 11-25 04:08 | SOL/USD | C-M15-tweezer-bottom | 4/5 | 69.49126 | 68.826851 | 70.487873 | $100.00 | order placed |
| 11-25 04:08 | SOL/USD | S13-ichimoku-short | 4/5 | 68.84811 | 70.773779 | 67.182286 | $100.00 | paper-graded (spot cannot short) |
| 11-25 04:08 | XRP/USD | C-M15-gravestone | 4/5 | 0.91785268 | 0.92456829 | 0.90777927 | $100.00 | paper-graded (spot cannot short) |

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
