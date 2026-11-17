# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-17 03:10 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $45,544.19 · equity $99,899.42

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$87.49 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (2)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| DOGE/USD | buy_stop | 0.05905615 | 124682 | $7,363 | $75.00 | 0.05872 | +0.57% | 0 min |
| ETH/USD | buy_stop | 1826.5448 | 3.74218 | $6,835 | $75.00 | 1813.76 | +0.70% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (4)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BTC/USD | 0.069084 | 63278.87 | 64579.4 | $89.85 | 63069.244 | 66371.462 | +1.80R |
| LINK/USD | 550.862 | 9.2056144 | 9.141 | $-35.59 | 9.0694641 | 9.3822154 | -0.47R |
| SOL/USD | 54.3458 | 71.398586 | 72.17 | $41.92 | 70.018534 | 72.918795 | +0.56R |
| XRP/USD | 4643.61 | 0.95972892 | 0.9591 | $-2.92 | 0.94357771 | 0.97833374 | -0.04R |

## Last 12 signals (236 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-17 03:10 | AVAX/USD | S18-rsi2-short | 4/5 | 7.121 | 7.231304 | 6.98312 | $100.00 | paper-graded (spot cannot short) |
| 11-17 03:10 | LINK/USD | S22-rsi-bull-div | 3/5 | 9.1325258 | 9.0336854 | 9.2807865 | $75.00 | not fired (guard/duplicate) |
| 11-17 03:10 | DOGE/USD | C-H1-tweezer-bottom | 3/5 | 0.05905615 | 0.05845462 | 0.05995844 | $75.00 | order placed |
| 11-17 03:10 | DOGE/USD | S21-pivot-S1-short | 4/5 | 0.05890718 | 0.06237667 | 0.05216667 | $100.00 | paper-graded (spot cannot short) |
| 11-17 03:10 | SOL/USD | C-M15-shooting-star | 4/5 | 71.456105 | 72.059737 | 70.550657 | $100.00 | not fired (guard/duplicate) |
| 11-17 03:10 | SOL/USD | C-H1-tweezer-bottom | 3/5 | 71.983895 | 71.090263 | 73.324343 | $75.00 | not fired (guard/duplicate) |
| 11-17 03:10 | SOL/USD | C-H1-bull-engulfing | 3/5 | 71.983895 | 71.090263 | 73.324343 | $75.00 | not fired (guard/duplicate) |
| 11-17 03:10 | SOL/USD | S13-ichimoku-long | 3/5 | 72.345842 | 71.133315 | 74.065687 | $75.00 | not fired (guard/duplicate) |
| 11-17 03:10 | XRP/USD | C-M15-tweezer-bottom | 3/5 | 0.95765947 | 0.95015132 | 0.9689217 | $75.00 | not fired (guard/duplicate) |
| 11-17 03:10 | XRP/USD | C-H1-tweezer-bottom | 3/5 | 0.96055947 | 0.94815132 | 0.9791717 | $75.00 | not fired (guard/duplicate) |
| 11-17 03:10 | ETH/USD | C-H1-tweezer-bottom | 3/5 | 1826.5448 | 1806.503 | 1856.6075 | $75.00 | order placed |
| 11-17 03:10 | BTC/USD | C-M15-tweezer-bottom | 3/5 | 64661.184 | 64221.091 | 65321.323 | $75.00 | not fired (guard/duplicate) |

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
