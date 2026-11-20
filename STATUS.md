# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-20 12:47 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $37,812.51 · equity $97,454.64

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$217.70 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (6)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_stop | 62376.702 | 0.12639 | $7,884 | $117.00 | 61581.9 | +1.29% | 0 min |
| DOGE/USD | buy_stop | 0.05758516 | 105004 | $6,047 | $88.00 | 0.0565 | +1.92% | 0 min |
| DOGE/USD | buy_stop | 0.05675516 | 176686 | $10,028 | $88.00 | 0.0565 | +0.45% | 0 min |
| LINK/USD | buy_stop | 8.9277002 | 644.921 | $5,758 | $88.00 | 8.754 | +1.98% | 0 min |
| SOL/USD | buy_stop | 71.46777 | 111.789 | $7,989 | $88.00 | 71.09 | +0.53% | 0 min |
| XRP/USD | buy_stop | 0.96904917 | 6996.73 | $6,780 | $117.00 | 0.9463 | +2.40% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (507 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-20 12:47 | BCH/USD | S13-ichimoku-short | 4/5 | 196.20005 | 206.46489 | 190.8708 | $117.00 | paper-graded (spot cannot short) |
| 11-20 12:47 | LTC/USD | S2-breakdown-short | 4/5 | 41.066406 | 42.163594 | 39.420626 | $117.00 | paper-graded (spot cannot short) |
| 11-20 12:47 | LINK/USD | C-H1-bull-engulfing | 3/5 | 8.9277002 | 8.7912494 | 9.1323766 | $88.00 | order placed |
| 11-20 12:47 | LINK/USD | S2-breakdown-short | 4/5 | 8.7222494 | 8.9487506 | 8.3824975 | $117.00 | paper-graded (spot cannot short) |
| 11-20 12:47 | DOGE/USD | C-M15-bull-harami | 3/5 | 0.05675516 | 0.0562571 | 0.05750224 | $88.00 | order placed |
| 11-20 12:47 | DOGE/USD | C-H1-tweezer-bottom | 3/5 | 0.05758516 | 0.0567471 | 0.05884224 | $88.00 | order placed |
| 11-20 12:47 | SOL/USD | C-M15-bull-harami | 3/5 | 71.46777 | 70.680575 | 72.648561 | $88.00 | order placed |
| 11-20 12:47 | XRP/USD | C-H1-tweezer-bottom | 4/5 | 0.96904917 | 0.95232707 | 0.99413233 | $117.00 | order placed |
| 11-20 12:47 | ETH/USD | S1-pullback-short | 4/5 | 1755.8114 | 1774.7915 | 1727.3412 | $117.00 | paper-graded (spot cannot short) |
| 11-20 12:47 | BTC/USD | C-H1-bull-engulfing | 4/5 | 62376.702 | 61450.995 | 63765.263 | $117.00 | order placed |
| 11-20 05:29 | AVAX/USD | S21-pivot-S1-short | 4/5 | 6.9207825 | 7.1086667 | 6.5736667 | $100.00 | paper-graded (spot cannot short) |
| 11-20 05:29 | AVAX/USD | S13-ichimoku-short | 4/5 | 6.8366738 | 7.0306524 | 6.6408822 | $100.00 | paper-graded (spot cannot short) |

## Accuracy so far

14 graded outcomes (5 win / 8 loss / 1 scratch) · win rate 38% · avg -0.05R · sizing today: score 3 -> $88.00 · score 4 -> $117.00 · score 5 -> $146.00

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
