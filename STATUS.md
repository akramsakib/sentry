# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-22 10:15 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-33,514.50 · equity $98,285.89

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$253.34 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (6)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| ADA/USD | buy_stop | 0.14587336 | 14648.2 | $2,137 | $75.00 | 0.1456 | +0.19% | 0 min |
| BTC/USD | buy_stop | 61438.243 | 0.0677805 | $4,164 | $100.00 | 60989.7 | +0.74% | 0 min |
| SOL/USD | buy_stop | 70.717305 | 35.7668 | $2,529 | $75.00 | 70.6 | +0.17% | 0 min |
| XRP/USD | buy_stop | 0.93483322 | 2613.27 | $2,443 | $75.00 | 0.9333 | +0.16% | 0 min |
| XRP/USD | buy_stop | 0.9333 | 4772.05 | $4,454 | $100.00 | 0.9333 | +0.00% | 0 min |
| XRP/USD | buy_stop | 0.9333 | 4772.05 | $4,454 | $100.00 | 0.9333 | +0.00% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (606 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-22 10:15 | LINK/USD | S21-pivot-S1-short | 4/5 | 8.8313124 | 9.058 | 8.407 | $100.00 | paper-graded (spot cannot short) |
| 11-22 10:15 | LINK/USD | S4-band-fade-short | 4/5 | 8.6995604 | 8.8261257 | 8.599 | $100.00 | paper-graded (spot cannot short) |
| 11-22 10:15 | ADA/USD | S13-ichimoku-long | 3/5 | 0.14587336 | 0.14075328 | 0.14960926 | $75.00 | order placed |
| 11-22 10:15 | SOL/USD | S13-ichimoku-long | 3/5 | 70.717305 | 68.620391 | 72.320469 | $75.00 | order placed |
| 11-22 10:15 | XRP/USD | C-H1-three-outside-up | 4/5 | 0.93262214 | 0.91234464 | 0.9630384 | $100.00 | order placed |
| 11-22 10:15 | XRP/USD | C-H1-bull-engulfing | 4/5 | 0.93262214 | 0.91234464 | 0.9630384 | $100.00 | order placed |
| 11-22 10:15 | XRP/USD | S13-ichimoku-long | 3/5 | 0.93483322 | 0.90613357 | 0.95578718 | $75.00 | order placed |
| 11-22 10:15 | ETH/USD | S4-band-fade-short | 4/5 | 1706.3256 | 1725.0833 | 1679.8365 | $100.00 | paper-graded (spot cannot short) |
| 11-22 10:15 | BTC/USD | C-M15-three-soldiers | 4/5 | 61438.243 | 59962.893 | 63651.268 | $100.00 | order placed |
| 11-22 10:15 | BTC/USD | S4-band-fade-short | 4/5 | 60991.528 | 61409.958 | 59916.04 | $100.00 | paper-graded (spot cannot short) |
| 11-22 02:32 | AVAX/USD | C-H1-bear-harami | 3/5 | 6.5526053 | 6.6039867 | 6.4755333 | $75.00 | paper-graded (spot cannot short) |
| 11-22 02:32 | BCH/USD | C-H1-bear-harami | 4/5 | 198.86598 | 200.97006 | 195.70986 | $100.00 | paper-graded (spot cannot short) |

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
