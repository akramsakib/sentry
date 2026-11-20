# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-20 14:18 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $37,812.51 · equity $97,850.69

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$217.70 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (6)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_stop | 62376.702 | 0.12639 | $7,884 | $117.00 | 61896.6 | +0.78% | 91 min |
| DOGE/USD | buy_stop | 0.05758516 | 105004 | $6,047 | $88.00 | 0.05665 | +1.65% | 91 min |
| DOGE/USD | buy_stop | 0.05675516 | 176686 | $10,028 | $88.00 | 0.05665 | +0.19% | 91 min |
| LINK/USD | buy_stop | 8.9277002 | 644.921 | $5,758 | $88.00 | 8.799 | +1.46% | 91 min |
| SOL/USD | buy_stop | 71.46777 | 111.789 | $7,989 | $88.00 | 71.35 | +0.17% | 91 min |
| XRP/USD | buy_stop | 0.96904917 | 6996.73 | $6,780 | $117.00 | 0.9505 | +1.95% | 91 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (523 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-20 14:18 | AVAX/USD | S25-session-break-short | 4/5 | 6.8471415 | 6.9407169 | 6.6875643 | $150.00 | paper-graded (spot cannot short) |
| 11-20 14:18 | AVAX/USD | S11-dc55-short | 4/5 | 6.7931415 | 6.8551507 | 6.607114 | $150.00 | paper-graded (spot cannot short) |
| 11-20 14:18 | AVAX/USD | S11-dc20-short | 4/5 | 6.7931415 | 6.8551507 | 6.607114 | $150.00 | paper-graded (spot cannot short) |
| 11-20 14:18 | BCH/USD | C-H1-marubozu | 4/5 | 195.77399 | 199.95004 | 189.50991 | $150.00 | paper-graded (spot cannot short) |
| 11-20 14:18 | BCH/USD | S1-pullback-short | 3/5 | 202.99752 | 208.45004 | 194.81873 | $112.00 | paper-graded (spot cannot short) |
| 11-20 14:18 | LTC/USD | S18-rsi2-short | 4/5 | 41.66 | 42.217567 | 40.963042 | $150.00 | paper-graded (spot cannot short) |
| 11-20 14:18 | ETH/USD | S3-momentum-short | 4/5 | 1724.3328 | 1753.7544 | 1667.5367 | $150.00 | paper-graded (spot cannot short) |
| 11-20 13:43 | AVAX/USD | C-H1-three-outside-down | 5/5 | 6.8472601 | 6.9448497 | 6.7008758 | $146.00 | paper-graded (spot cannot short) |
| 11-20 13:43 | BCH/USD | S3-momentum-short | 4/5 | 198.56568 | 202.88865 | 190.18406 | $117.00 | paper-graded (spot cannot short) |
| 11-20 13:43 | BCH/USD | S11-dc55-short | 4/5 | 200.39568 | 202.24594 | 194.84488 | $117.00 | paper-graded (spot cannot short) |
| 11-20 13:43 | BCH/USD | S11-dc20-short | 4/5 | 200.39568 | 202.24594 | 194.84488 | $117.00 | paper-graded (spot cannot short) |
| 11-20 13:43 | BCH/USD | S18-rsi2-short | 3/5 | 197.69 | 200.86188 | 193.72515 | $88.00 | paper-graded (spot cannot short) |

## Accuracy so far

14 graded outcomes (5 win / 8 loss / 1 scratch) · win rate 38% · avg -0.05R · sizing today: score 3 -> $112.00 · score 4 -> $150.00 · score 5 -> $188.00

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
