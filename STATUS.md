# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-17 10:21 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $45,544.19 · equity $99,611.44

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$87.49 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (2)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BCH/USD | buy_stop | 209.26724 | 28.7168 | $6,009 | $75.00 | 208.76 | +0.24% | 0 min |
| ETH/USD | buy_limit | 1798.14 | 7.31746 | $13,158 | $75.00 | 1799.8 | -0.09% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (4)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BTC/USD | 0.069084 | 63278.87 | 64258.47 | $67.67 | 63069.244 | 66371.462 | +1.35R |
| LINK/USD | 550.862 | 9.2056144 | 9.116 | $-49.37 | 9.0694641 | 9.3822154 | -0.66R |
| SOL/USD | 54.3458 | 71.398586 | 72.29 | $48.44 | 70.018534 | 72.918795 | +0.65R |
| XRP/USD | 4643.61 | 0.95972892 | 0.9558 | $-18.24 | 0.94357771 | 0.97833374 | -0.24R |

## Last 12 signals (263 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-17 10:21 | BCH/USD | S13-ichimoku-long | 3/5 | 209.26724 | 206.65552 | 213.3295 | $75.00 | order placed |
| 11-17 10:21 | LTC/USD | C-H1-three-outside-down | 4/5 | 44.510238 | 44.879404 | 43.95649 | $100.00 | paper-graded (spot cannot short) |
| 11-17 10:21 | LTC/USD | C-H1-tweezer-top | 4/5 | 44.510238 | 44.879404 | 43.95649 | $100.00 | paper-graded (spot cannot short) |
| 11-17 10:21 | LTC/USD | S21-pivot-S1-short | 4/5 | 44.506905 | 47.243333 | 39.153333 | $100.00 | paper-graded (spot cannot short) |
| 11-17 10:21 | LINK/USD | C-H1-three-outside-down | 4/5 | 9.1247821 | 9.1990448 | 9.013388 | $100.00 | not fired (guard/duplicate) |
| 11-17 10:21 | LINK/USD | C-H1-marubozu | 4/5 | 9.1247821 | 9.1990448 | 9.013388 | $100.00 | not fired (guard/duplicate) |
| 11-17 10:21 | LINK/USD | S13-ichimoku-short | 4/5 | 9.1161731 | 9.2086538 | 8.9272057 | $100.00 | not fired (guard/duplicate) |
| 11-17 10:21 | DOGE/USD | C-H1-three-outside-down | 5/5 | 0.05861252 | 0.05923371 | 0.05768074 | $125.00 | paper-graded (spot cannot short) |
| 11-17 10:21 | DOGE/USD | C-H1-tweezer-top | 5/5 | 0.05861252 | 0.05923371 | 0.05768074 | $125.00 | paper-graded (spot cannot short) |
| 11-17 10:21 | DOGE/USD | C-H1-bear-engulfing | 5/5 | 0.05861252 | 0.05923371 | 0.05768074 | $125.00 | paper-graded (spot cannot short) |
| 11-17 10:21 | SOL/USD | C-H1-tweezer-top | 5/5 | 72.110774 | 73.138065 | 70.569838 | $125.00 | not fired (guard/duplicate) |
| 11-17 10:21 | SOL/USD | S1-pullback-long | 4/5 | 72.093616 | 71.831935 | 72.486136 | $100.00 | not fired (guard/duplicate) |

## Accuracy so far

1 graded outcomes (0 win / 1 loss) · win rate 0% · avg -0.61R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

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
