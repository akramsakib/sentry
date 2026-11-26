# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-26 14:53 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-210,735.69 · equity $101,730.84

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$350.35 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (2)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| LINK/USD | buy_limit | 9.227 | 935.557 | $8,632 | $100.00 | 9.231 | -0.04% | 0 min |
| LTC/USD | buy_limit | 43.66 | 190.37 | $8,312 | $100.00 | 43.71 | -0.11% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (3)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| ETH/USD | 9.00073 | 1689.5815 | 1695.72 | $55.25 | 1678.4713 | 1706.2468 | +0.55R |
| SOL/USD | 89.9789 | 70.29 | 70.96 | $60.29 | 69.188628 | 71.689215 | +0.60R |
| XRP/USD | 5578.33 | 0.9326 | 0.9486 | $89.25 | 0.92035512 | 0.95060611 | +1.19R |

## Last 12 signals (773 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-26 14:53 | AVAX/USD | C-M15-three-inside-down | 5/5 | 6.6112244 | 6.659439 | 6.5389024 | $125.00 | paper-graded (spot cannot short) |
| 11-26 14:53 | AVAX/USD | C-M15-tweezer-top | 5/5 | 6.6112244 | 6.659439 | 6.5389024 | $125.00 | paper-graded (spot cannot short) |
| 11-26 14:53 | AVAX/USD | C-H1-bear-harami | 3/5 | 6.6252244 | 6.696439 | 6.5184024 | $75.00 | paper-graded (spot cannot short) |
| 11-26 14:53 | AVAX/USD | S21-pivot-S1-short | 4/5 | 6.6458911 | 6.9383333 | 6.0783333 | $100.00 | paper-graded (spot cannot short) |
| 11-26 14:53 | BCH/USD | C-M15-bear-harami | 3/5 | 208.08092 | 209.37771 | 206.13573 | $75.00 | paper-graded (spot cannot short) |
| 11-26 14:53 | BCH/USD | C-H1-tweezer-top | 3/5 | 206.65092 | 208.73771 | 203.52073 | $75.00 | paper-graded (spot cannot short) |
| 11-26 14:53 | LTC/USD | C-M15-bear-harami | 3/5 | 43.726226 | 44.019436 | 43.28641 | $75.00 | paper-graded (spot cannot short) |
| 11-26 14:53 | LTC/USD | S18-rsi2-long | 4/5 | 43.66 | 43.134707 | 44.316616 | $100.00 | order placed |
| 11-26 14:53 | LINK/USD | S18-rsi2-long | 4/5 | 9.227 | 9.1201119 | 9.3606102 | $100.00 | order placed |
| 11-26 14:53 | ADA/USD | C-M15-tweezer-top | 5/5 | 0.14874466 | 0.14978835 | 0.14717913 | $125.00 | paper-graded (spot cannot short) |
| 11-26 14:53 | ADA/USD | C-M15-bear-engulfing | 5/5 | 0.14874466 | 0.14978835 | 0.14717913 | $125.00 | paper-graded (spot cannot short) |
| 11-26 14:53 | ADA/USD | C-H1-shooting-star | 4/5 | 0.14824466 | 0.14998835 | 0.14562913 | $100.00 | paper-graded (spot cannot short) |

## Accuracy so far

14 graded outcomes (5 win / 8 loss / 1 scratch) · win rate 38% · avg -0.05R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 2 new order(s), 10 symbols scanned

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
