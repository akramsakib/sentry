# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-18 15:28 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $62,110.31 · equity $99,600.66

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$130.92 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (1)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| ETH/USD | buy_stop | 1778.1605 | 1.77043 | $3,148 | $50.00 | 1773.95 | +0.24% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (5)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| ADA/USD | 20659.4 | 0.15347 | 0.15215 | $-27.27 | 0.1510798 | 0.15652524 | -0.55R |
| BTC/USD | 0.0909312 | 64180 | 63518.08 | $-60.19 | 63355.2 | 65042.397 | -0.80R |
| DOGE/USD | 54931.8 | 0.05911149 | 0.059 | $-6.12 | 0.05820127 | 0.06047682 | -0.12R |
| SOL/USD | 54.3458 | 71.398586 | 73.89 | $135.40 | 70.018534 | 72.918795 | +1.81R |
| XRP/USD | 4643.61 | 0.95972892 | 0.982 | $103.42 | 0.94357771 | 0.97833374 | +1.38R |

## Last 12 signals (379 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-18 15:28 | BCH/USD | S1-pullback-short | 4/5 | 208.55811 | 210.09998 | 206.24531 | $50.00 | paper-graded (spot cannot short) |
| 11-18 15:28 | LTC/USD | S13-ichimoku-short | 4/5 | 43.748841 | 44.667317 | 42.913007 | $50.00 | paper-graded (spot cannot short) |
| 11-18 15:28 | LINK/USD | C-H1-shooting-star | 4/5 | 9.1088756 | 9.192811 | 8.9829724 | $50.00 | paper-graded (spot cannot short) |
| 11-18 15:28 | ADA/USD | C-M15-bull-harami | 3/5 | 0.15316442 | 0.15148896 | 0.15567761 | $50.00 | not fired (guard/duplicate) |
| 11-18 15:28 | ADA/USD | C-H1-three-inside-up | 4/5 | 0.15446442 | 0.15218896 | 0.15787761 | $50.00 | not fired (guard/duplicate) |
| 11-18 15:28 | ADA/USD | C-H1-bull-engulfing | 4/5 | 0.15446442 | 0.15218896 | 0.15787761 | $50.00 | not fired (guard/duplicate) |
| 11-18 15:28 | DOGE/USD | C-H1-shooting-star | 4/5 | 0.05911402 | 0.05959994 | 0.05838514 | $50.00 | not fired (guard/duplicate) |
| 11-18 15:28 | SOL/USD | C-M15-tweezer-bottom | 4/5 | 74.242881 | 73.272797 | 75.698008 | $50.00 | not fired (guard/duplicate) |
| 11-18 15:28 | XRP/USD | C-M15-tweezer-bottom | 4/5 | 0.98698224 | 0.9740944 | 1.006314 | $50.00 | not fired (guard/duplicate) |
| 11-18 15:28 | XRP/USD | S22-rsi-bull-div | 3/5 | 0.98698224 | 0.9733944 | 1.007364 | $50.00 | not fired (guard/duplicate) |
| 11-18 15:28 | ETH/USD | C-M15-tweezer-bottom | 3/5 | 1778.1605 | 1749.9188 | 1820.5231 | $50.00 | order placed |
| 11-18 15:28 | BTC/USD | C-M15-tweezer-bottom | 4/5 | 63719.723 | 63009.694 | 64784.766 | $50.00 | not fired (guard/duplicate) |

## Accuracy so far

6 graded outcomes (1 win / 4 loss / 1 scratch) · win rate 20% · avg -0.22R · sizing today: score 3 -> $56.00 · score 4 -> $75.00 · score 5 -> $94.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 1 new order(s), 10 symbols scanned

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
