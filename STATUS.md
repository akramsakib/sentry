# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-17 18:28 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $69,434.95 · equity $99,457.03

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$118.58 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (2)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_stop | 64180 | 0.0909312 | $5,836 | $75.00 | 63667.7 | +0.80% | 34 min |
| ETH/USD | buy_stop | 1800.05 | 2.07483 | $3,735 | $50.00 | 1784.58 | +0.87% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (3)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| LINK/USD | 550.862 | 9.2056144 | 9.13 | $-41.65 | 9.0694641 | 9.3822154 | -0.56R |
| SOL/USD | 54.3458 | 71.398586 | 72.76 | $73.99 | 70.018534 | 72.918795 | +0.99R |
| XRP/USD | 4643.61 | 0.95972892 | 0.9616 | $8.69 | 0.94357771 | 0.97833374 | +0.12R |

## Last 12 signals (310 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-17 18:28 | BCH/USD | C-M15-three-outside-down | 4/5 | 206.56396 | 208.30509 | 203.95227 | $50.00 | paper-graded (spot cannot short) |
| 11-17 18:28 | BCH/USD | C-M15-tweezer-top | 4/5 | 206.56396 | 208.30509 | 203.95227 | $50.00 | paper-graded (spot cannot short) |
| 11-17 18:28 | BCH/USD | C-M15-bear-engulfing | 4/5 | 206.56396 | 208.30509 | 203.95227 | $50.00 | paper-graded (spot cannot short) |
| 11-17 18:28 | LINK/USD | C-M15-evening-star | 4/5 | 9.0783366 | 9.1651584 | 8.9481039 | $50.00 | not fired (guard/duplicate) |
| 11-17 18:28 | ADA/USD | S18-rsi2-short | 4/5 | 0.1526 | 0.1551148 | 0.1494565 | $50.00 | paper-graded (spot cannot short) |
| 11-17 18:28 | DOGE/USD | S18-rsi2-short | 4/5 | 0.05888 | 0.0597379 | 0.05780762 | $50.00 | paper-graded (spot cannot short) |
| 11-17 18:28 | ETH/USD | C-M15-bull-engulfing | 3/5 | 1791.1373 | 1775.9517 | 1813.9158 | $50.00 | order placed |
| 11-17 18:28 | ETH/USD | S18-rsi2-short | 4/5 | 1800.05 | 1827.4979 | 1765.7401 | $50.00 | paper-graded (spot cannot short) |
| 11-17 18:06 | LINK/USD | C-M15-bear-harami | 3/5 | 9.0783366 | 9.1651584 | 8.9481039 | $75.00 | not fired (guard/duplicate) |
| 11-17 18:06 | SOL/USD | C-M15-hammer/takuri | 3/5 | 72.432794 | 71.733016 | 73.48246 | $75.00 | not fired (guard/duplicate) |
| 11-17 18:06 | ETH/USD | C-M15-dragonfly | 3/5 | 1787.4873 | 1769.9917 | 1813.7308 | $75.00 | not fired (guard/duplicate) |
| 11-17 17:54 | AVAX/USD | C-M15-shooting-star | 4/5 | 7.0606976 | 7.148756 | 6.92861 | $100.00 | paper-graded (spot cannot short) |

## Accuracy so far

4 graded outcomes (1 win / 3 loss) · win rate 25% · avg -0.05R · sizing today: score 3 -> $50.00 · score 4 -> $50.00 · score 5 -> $62.00

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
