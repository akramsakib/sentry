# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-19 01:09 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $57,449.57 · equity $99,318.23

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$180.42 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (3)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_stop | 63334.986 | 0.0393824 | $2,494 | $50.00 | 63154.5 | +0.29% | 0 min |
| BTC/USD | buy_stop | 63334.986 | 0.0393824 | $2,494 | $50.00 | 63154.5 | +0.29% | 0 min |
| BTC/USD | buy_stop | 63231.486 | 0.0840757 | $5,316 | $50.00 | 63154.5 | +0.12% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (3)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| DOGE/USD | 157867 | 0.05807 | 0.05885 | $123.14 | 0.05790527 | 0.0593965 | +2.20R |
| SOL/USD | 108.486 | 72.53 | 73.48 | $103.06 | 72.273804 | 74.428 | +1.84R |
| XRP/USD | 4643.61 | 0.95972892 | 0.9667 | $32.37 | 0.94357771 | 0.97833374 | +0.43R |

## Last 12 signals (435 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-19 01:09 | ADA/USD | S18-rsi2-short | 4/5 | 0.1518 | 0.15394171 | 0.14912286 | $50.00 | paper-graded (spot cannot short) |
| 11-19 01:09 | SOL/USD | C-M15-morning-star | 4/5 | 73.837139 | 73.062153 | 74.999617 | $50.00 | not fired (guard/duplicate) |
| 11-19 01:09 | SOL/USD | C-H1-three-inside-up | 4/5 | 74.027139 | 72.282153 | 76.644617 | $50.00 | not fired (guard/duplicate) |
| 11-19 01:09 | XRP/USD | C-M15-morning-star | 4/5 | 0.97029645 | 0.96035887 | 0.98520283 | $50.00 | not fired (guard/duplicate) |
| 11-19 01:09 | XRP/USD | C-H1-bull-engulfing | 4/5 | 0.97439645 | 0.95595887 | 1.0020528 | $50.00 | not fired (guard/duplicate) |
| 11-19 01:09 | XRP/USD | S13-ichimoku-short | 4/5 | 0.96705532 | 0.98418936 | 0.94457803 | $50.00 | not fired (guard/duplicate) |
| 11-19 01:09 | XRP/USD | S18-rsi2-short | 4/5 | 0.9687 | 0.98185744 | 0.9522532 | $50.00 | not fired (guard/duplicate) |
| 11-19 01:09 | BTC/USD | C-M15-morning-star | 3/5 | 63231.486 | 62636.784 | 64123.54 | $50.00 | order placed |
| 11-19 01:09 | BTC/USD | C-H1-three-inside-up | 3/5 | 63334.986 | 62065.384 | 65239.39 | $50.00 | order placed |
| 11-19 01:09 | BTC/USD | C-H1-morning-star | 3/5 | 63334.986 | 62065.384 | 65239.39 | $50.00 | order placed |
| 11-19 01:09 | BTC/USD | S21-pivot-S1-short | 4/5 | 63598.347 | 64655.467 | 61656.567 | $50.00 | paper-graded (spot cannot short) |
| 11-18 19:08 | ADA/USD | S13-ichimoku-short | 4/5 | 0.15163434 | 0.15328132 | 0.14800364 | $62.00 | paper-graded (spot cannot short) |

## Accuracy so far

11 graded outcomes (2 win / 8 loss / 1 scratch) · win rate 20% · avg -0.37R · sizing today: score 3 -> $50.00 · score 4 -> $50.00 · score 5 -> $62.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 3 new order(s), 10 symbols scanned

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
