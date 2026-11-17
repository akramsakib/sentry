# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-17 17:54 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $35,604.34 · equity $99,449.74

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$105.11 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (1)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_stop | 64180 | 0.0909312 | $5,836 | $75.00 | 63779 | +0.63% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (5)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BCH/USD | 28.7168 | 209.26724 | 207.46 | $-51.90 | 206.65552 | 213.3295 | -0.69R |
| ETH/USD | 7.31746 | 1793.72 | 1785.69 | $-58.76 | 1787.8905 | 1824.216 | -0.78R |
| LINK/USD | 550.862 | 9.2056144 | 9.113 | $-51.02 | 9.0694641 | 9.3822154 | -0.68R |
| SOL/USD | 54.3458 | 71.398586 | 72.35 | $51.71 | 70.018534 | 72.918795 | +0.69R |
| XRP/USD | 4643.61 | 0.95972892 | 0.9591 | $-2.92 | 0.94357771 | 0.97833374 | -0.04R |

## Last 12 signals (299 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-17 17:54 | AVAX/USD | C-M15-shooting-star | 4/5 | 7.0606976 | 7.148756 | 6.92861 | $100.00 | paper-graded (spot cannot short) |
| 11-17 17:54 | AVAX/USD | S13-ichimoku-short | 4/5 | 7.0945464 | 7.1554072 | 6.8833471 | $100.00 | paper-graded (spot cannot short) |
| 11-17 17:54 | BCH/USD | C-M15-gravestone | 4/5 | 206.89481 | 209.07299 | 203.62754 | $100.00 | not fired (guard/duplicate) |
| 11-17 17:54 | BCH/USD | S10-ma-cross-short | 4/5 | 206.98961 | 210.42233 | 201.59534 | $100.00 | not fired (guard/duplicate) |
| 11-17 17:54 | LTC/USD | C-M15-tweezer-top | 4/5 | 44.131462 | 44.581345 | 43.456637 | $100.00 | paper-graded (spot cannot short) |
| 11-17 17:54 | LTC/USD | C-M15-shooting-star | 4/5 | 44.131462 | 44.581345 | 43.456637 | $100.00 | paper-graded (spot cannot short) |
| 11-17 17:54 | LTC/USD | S16-inside-short | 4/5 | 44.021462 | 44.601345 | 43.341928 | $100.00 | paper-graded (spot cannot short) |
| 11-17 17:54 | LINK/USD | C-M15-shooting-star | 4/5 | 9.0983087 | 9.1992283 | 8.9469292 | $100.00 | not fired (guard/duplicate) |
| 11-17 17:54 | ADA/USD | C-M15-gravestone | 4/5 | 0.15149047 | 0.15332383 | 0.14874042 | $100.00 | paper-graded (spot cannot short) |
| 11-17 17:54 | DOGE/USD | C-M15-shooting-star | 4/5 | 0.05834924 | 0.0589569 | 0.05743775 | $100.00 | paper-graded (spot cannot short) |
| 11-17 17:54 | DOGE/USD | S13-ichimoku-short | 4/5 | 0.05855386 | 0.05888728 | 0.05710327 | $100.00 | paper-graded (spot cannot short) |
| 11-17 17:54 | SOL/USD | C-H1-three-inside-down | 5/5 | 70.897991 | 74.245021 | 65.877446 | $125.00 | not fired (guard/duplicate) |

## Accuracy so far

2 graded outcomes (1 win / 1 loss) · win rate 50% · avg +0.79R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

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
