# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-22 17:52 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-33,514.50 · equity $98,183.02

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$253.34 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (6)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| ADA/USD | buy_stop | 0.14486542 | 76611.1 | $11,098 | $75.00 | 0.1447 | +0.11% | 0 min |
| ADA/USD | buy_stop | 0.14486542 | 76611.1 | $11,098 | $75.00 | 0.1447 | +0.11% | 0 min |
| BTC/USD | buy_stop | 60951.814 | 0.196876 | $12,000 | $75.00 | 60885.9 | +0.11% | 0 min |
| SOL/USD | buy_stop | 70.520651 | 171.516 | $12,095 | $75.00 | 70.42 | +0.14% | 0 min |
| XRP/USD | buy_stop | 0.9295332 | 11250.8 | $10,458 | $75.00 | 0.9279 | +0.18% | 0 min |
| XRP/USD | buy_stop | 0.9295332 | 11250.8 | $10,458 | $75.00 | 0.9279 | +0.18% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (615 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-22 17:52 | BCH/USD | C-H1-evening-star | 4/5 | 197.14549 | 198.98128 | 194.3918 | $100.00 | paper-graded (spot cannot short) |
| 11-22 17:52 | LTC/USD | C-H1-tweezer-top | 4/5 | 39.669146 | 40.042136 | 39.109661 | $100.00 | paper-graded (spot cannot short) |
| 11-22 17:52 | ADA/USD | C-M15-bull-harami | 3/5 | 0.14486542 | 0.14388645 | 0.14633387 | $75.00 | order placed |
| 11-22 17:52 | ADA/USD | C-M15-tweezer-bottom | 3/5 | 0.14486542 | 0.14388645 | 0.14633387 | $75.00 | order placed |
| 11-22 17:52 | SOL/USD | C-M15-tweezer-bottom | 3/5 | 70.520651 | 70.083373 | 71.176568 | $75.00 | order placed |
| 11-22 17:52 | SOL/USD | C-H1-tweezer-top | 4/5 | 70.009349 | 70.706627 | 68.963432 | $100.00 | paper-graded (spot cannot short) |
| 11-22 17:52 | XRP/USD | C-M15-bull-harami | 3/5 | 0.9295332 | 0.922867 | 0.93953249 | $75.00 | order placed |
| 11-22 17:52 | XRP/USD | C-M15-tweezer-bottom | 3/5 | 0.9295332 | 0.922867 | 0.93953249 | $75.00 | order placed |
| 11-22 17:52 | BTC/USD | C-M15-tweezer-bottom | 3/5 | 60951.814 | 60570.864 | 61523.239 | $75.00 | order placed |
| 11-22 10:15 | LINK/USD | S21-pivot-S1-short | 4/5 | 8.8313124 | 9.058 | 8.407 | $100.00 | paper-graded (spot cannot short) |
| 11-22 10:15 | LINK/USD | S4-band-fade-short | 4/5 | 8.6995604 | 8.8261257 | 8.599 | $100.00 | paper-graded (spot cannot short) |
| 11-22 10:15 | ADA/USD | S13-ichimoku-long | 3/5 | 0.14587336 | 0.14075328 | 0.14960926 | $75.00 | order placed |

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
