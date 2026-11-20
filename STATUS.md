# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-20 21:52 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $37,812.51 · equity $95,298.59

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$217.70 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (6)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_stop | 59126.8 | 0.0683493 | $4,041 | $112.00 | 59310.8 | -0.31% | 0 min |
| ETH/USD | buy_stop | 1623.6 | 2.99246 | $4,859 | $112.00 | 1628.69 | -0.31% | 0 min |
| SOL/USD | buy_stop | 68.997237 | 59.564 | $4,110 | $112.00 | 68.95 | +0.07% | 0 min |
| SOL/USD | buy_stop | 68.99 | 69.9923 | $4,829 | $150.00 | 68.95 | +0.06% | 0 min |
| SOL/USD | buy_stop | 68.99 | 69.9923 | $4,829 | $150.00 | 68.95 | +0.06% | 0 min |
| XRP/USD | buy_stop | 0.911 | 3606.49 | $3,286 | $112.00 | 0.9101 | +0.10% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (544 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-20 21:52 | LINK/USD | S18-rsi2-short | 4/5 | 8.509 | 8.6819752 | 8.292781 | $150.00 | paper-graded (spot cannot short) |
| 11-20 21:52 | DOGE/USD | S3-momentum-short | 4/5 | 0.05266992 | 0.05407016 | 0.04995951 | $150.00 | paper-graded (spot cannot short) |
| 11-20 21:52 | DOGE/USD | S11-dc55-short | 4/5 | 0.05304992 | 0.05368049 | 0.05115819 | $150.00 | paper-graded (spot cannot short) |
| 11-20 21:52 | DOGE/USD | S11-dc20-short | 4/5 | 0.05304992 | 0.05368049 | 0.05115819 | $150.00 | paper-graded (spot cannot short) |
| 11-20 21:52 | DOGE/USD | S18-rsi2-short | 4/5 | 0.05409 | 0.05517098 | 0.05273877 | $150.00 | paper-graded (spot cannot short) |
| 11-20 21:52 | SOL/USD | C-M15-three-outside-up | 4/5 | 68.067237 | 66.846907 | 69.897733 | $150.00 | order placed |
| 11-20 21:52 | SOL/USD | C-M15-tweezer-bottom | 4/5 | 68.067237 | 66.846907 | 69.897733 | $150.00 | order placed |
| 11-20 21:52 | SOL/USD | S23-spring-long | 3/5 | 68.997237 | 67.116907 | 71.888529 | $112.00 | order placed |
| 11-20 21:52 | SOL/USD | S13-ichimoku-short | 4/5 | 68.814144 | 71.381712 | 66.410779 | $150.00 | paper-graded (spot cannot short) |
| 11-20 21:52 | SOL/USD | S18-rsi2-short | 3/5 | 68.99 | 70.396848 | 67.23144 | $112.00 | paper-graded (spot cannot short) |
| 11-20 21:52 | XRP/USD | S22-rsi-bull-div | 3/5 | 0.89876204 | 0.87994491 | 0.92698773 | $112.00 | order placed |
| 11-20 21:52 | XRP/USD | S3-momentum-short | 4/5 | 0.88933796 | 0.90912407 | 0.85122778 | $150.00 | paper-graded (spot cannot short) |

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
