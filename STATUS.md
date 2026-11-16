# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-16 02:52 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $82,783.16 · equity $100,006.48

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$68.88 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (5)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| ADA/USD | buy_stop | 0.15461567 | 39845.4 | $6,161 | $50.00 | 0.154 | +0.40% | 213 min |
| SOL/USD | buy_stop | 72.502469 | 80.8224 | $5,860 | $50.00 | 72.19 | +0.43% | 213 min |
| XRP/USD | buy_stop | 0.97241893 | 1222.29 | $1,189 | $50.00 | 0.9656 | +0.71% | 213 min |
| XRP/USD | buy_stop | 0.97184595 | 6484.39 | $6,302 | $50.00 | 0.9656 | +0.65% | 213 min |
| XRP/USD | buy_stop | 0.97184595 | 6484.39 | $6,302 | $50.00 | 0.9656 | +0.65% | 213 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (1)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BTC/USD | 0.069084 | 63278.87 | 64967.1 | $116.63 | 63069.244 | 66371.462 | +2.33R |

## Last 12 signals (148 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-16 02:52 | AVAX/USD | C-H1-three-outside-down | 5/5 | 7.1459071 | 7.3377323 | 6.8581693 | $62.00 | paper-graded (spot cannot short) |
| 11-16 02:52 | AVAX/USD | C-H1-tweezer-top | 5/5 | 7.1459071 | 7.3377323 | 6.8581693 | $62.00 | paper-graded (spot cannot short) |
| 11-16 02:52 | BCH/USD | C-H1-tweezer-top | 5/5 | 208.14212 | 211.51471 | 203.08323 | $62.00 | paper-graded (spot cannot short) |
| 11-16 02:52 | LTC/USD | C-H1-three-inside-down | 5/5 | 44.824549 | 45.658627 | 43.573432 | $62.00 | paper-graded (spot cannot short) |
| 11-16 02:52 | LINK/USD | C-H1-three-inside-down | 5/5 | 9.1188705 | 9.3333237 | 8.7971906 | $62.00 | paper-graded (spot cannot short) |
| 11-16 02:52 | ETH/USD | C-H1-three-inside-down | 5/5 | 1803.3036 | 1843.411 | 1743.1425 | $62.00 | paper-graded (spot cannot short) |
| 11-16 02:52 | ETH/USD | C-H1-tweezer-top | 5/5 | 1803.3036 | 1843.411 | 1743.1425 | $62.00 | paper-graded (spot cannot short) |
| 11-16 02:52 | BTC/USD | C-H1-three-inside-down | 5/5 | 64552.121 | 65527.047 | 63089.733 | $62.00 | not fired (guard/duplicate) |
| 11-16 02:52 | BTC/USD | C-H1-tweezer-top | 5/5 | 64552.121 | 65527.047 | 63089.733 | $62.00 | not fired (guard/duplicate) |
| 11-15 23:18 | LTC/USD | C-H1-tweezer-top | 4/5 | 45.104835 | 45.627913 | 44.320217 | $50.00 | paper-graded (spot cannot short) |
| 11-15 23:18 | LTC/USD | C-H1-bear-engulfing | 4/5 | 45.104835 | 45.627913 | 44.320217 | $50.00 | paper-graded (spot cannot short) |
| 11-15 23:18 | LINK/USD | C-M15-evening-star | 5/5 | 9.2370168 | 9.3059581 | 9.1336048 | $62.00 | paper-graded (spot cannot short) |

## Accuracy so far

1 graded outcomes (0 win / 1 loss) · win rate 0% · avg -0.61R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

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
