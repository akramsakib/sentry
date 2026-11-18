# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-18 03:46 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $58,427.35 · equity $99,900.86

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$129.07 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (0)

_None. Every symbol is scanned each cycle; a resting entry above is a trigger waiting to be hit, not a position._

## Positions (6)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| ADA/USD | 20659.4 | 0.15347 | 0.15341 | $-1.24 | 0.1510798 | 0.15652524 | -0.02R |
| BTC/USD | 0.0909312 | 64180 | 64465.92 | $26.00 | 63355.2 | 65042.397 | +0.35R |
| DOGE/USD | 54931.8 | 0.05911149 | 0.05937 | $14.20 | 0.05820127 | 0.06047682 | +0.28R |
| ETH/USD | 2.07483 | 1800.05 | 1805.53 | $11.37 | 1775.9517 | 1813.9158 | +0.23R |
| SOL/USD | 54.3458 | 71.398586 | 74.92 | $191.37 | 70.018534 | 72.918795 | +2.55R |
| XRP/USD | 4643.61 | 0.95972892 | 0.9792 | $90.42 | 0.94357771 | 0.97833374 | +1.21R |

## Last 12 signals (356 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-18 03:46 | DOGE/USD | C-M15-bear-harami | 3/5 | 0.05910366 | 0.05951586 | 0.05848536 | $50.00 | not fired (guard/duplicate) |
| 11-18 03:46 | DOGE/USD | C-M15-hammer/takuri | 3/5 | 0.05941634 | 0.05900414 | 0.06003464 | $50.00 | not fired (guard/duplicate) |
| 11-18 03:46 | SOL/USD | C-H1-evening-star | 5/5 | 74.052304 | 75.164241 | 72.384398 | $62.00 | not fired (guard/duplicate) |
| 11-18 03:46 | SOL/USD | C-H1-marubozu | 5/5 | 74.052304 | 75.164241 | 72.384398 | $62.00 | not fired (guard/duplicate) |
| 11-18 03:46 | XRP/USD | C-M15-bear-harami | 3/5 | 0.97375349 | 0.98141627 | 0.96225932 | $50.00 | not fired (guard/duplicate) |
| 11-18 03:46 | XRP/USD | C-H1-marubozu | 4/5 | 0.97165349 | 0.98061627 | 0.95820932 | $50.00 | not fired (guard/duplicate) |
| 11-18 03:46 | ETH/USD | C-H1-evening-star | 5/5 | 1800.139 | 1824.9125 | 1762.9786 | $62.00 | not fired (guard/duplicate) |
| 11-18 03:46 | ETH/USD | C-H1-marubozu | 5/5 | 1800.139 | 1824.9125 | 1762.9786 | $62.00 | not fired (guard/duplicate) |
| 11-18 03:46 | BTC/USD | C-M15-tweezer-top | 3/5 | 64260.796 | 64607.66 | 63740.499 | $50.00 | not fired (guard/duplicate) |
| 11-18 03:46 | BTC/USD | C-M15-hammer/takuri | 3/5 | 64524.404 | 64177.54 | 65044.701 | $50.00 | not fired (guard/duplicate) |
| 11-18 03:46 | BTC/USD | C-H1-marubozu | 5/5 | 64208.496 | 64905.26 | 63163.349 | $62.00 | not fired (guard/duplicate) |
| 11-18 02:38 | AVAX/USD | C-H1-bear-harami | 5/5 | 7.2333954 | 7.3190114 | 7.1049716 | $62.00 | paper-graded (spot cannot short) |

## Accuracy so far

5 graded outcomes (1 win / 4 loss) · win rate 20% · avg -0.27R · sizing today: score 3 -> $50.00 · score 4 -> $50.00 · score 5 -> $62.00

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
