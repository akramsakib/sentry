# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-18 10:42 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $58,427.35 · equity $100,081.90

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$129.07 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (0)

_None. Every symbol is scanned each cycle; a resting entry above is a trigger waiting to be hit, not a position._

## Positions (6)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| ADA/USD | 20659.4 | 0.15347 | 0.15321 | $-5.37 | 0.1510798 | 0.15652524 | -0.11R |
| BTC/USD | 0.0909312 | 64180 | 64197.11 | $1.56 | 63355.2 | 65042.397 | +0.02R |
| DOGE/USD | 54931.8 | 0.05911149 | 0.05936 | $13.65 | 0.05820127 | 0.06047682 | +0.27R |
| ETH/USD | 2.07483 | 1800.05 | 1801.49 | $2.99 | 1775.9517 | 1813.9158 | +0.06R |
| SOL/USD | 54.3458 | 71.398586 | 74.63 | $175.61 | 70.018534 | 72.918795 | +2.34R |
| XRP/USD | 4643.61 | 0.95972892 | 0.9966 | $171.22 | 0.94357771 | 0.97833374 | +2.28R |

## Last 12 signals (367 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-18 10:42 | AVAX/USD | C-H1-three-outside-down | 5/5 | 7.1049275 | 7.2101812 | 6.947047 | $62.00 | paper-graded (spot cannot short) |
| 11-18 10:42 | LTC/USD | C-M15-three-outside-down | 5/5 | 44.250782 | 44.738046 | 43.519885 | $62.00 | paper-graded (spot cannot short) |
| 11-18 10:42 | LTC/USD | C-H1-bear-harami | 5/5 | 44.480782 | 44.888046 | 43.869885 | $62.00 | paper-graded (spot cannot short) |
| 11-18 10:42 | ADA/USD | C-H1-tweezer-top | 4/5 | 0.15393983 | 0.15560042 | 0.15144894 | $50.00 | not fired (guard/duplicate) |
| 11-18 10:42 | ADA/USD | S13-ichimoku-long | 3/5 | 0.15334025 | 0.15221949 | 0.15662372 | $50.00 | not fired (guard/duplicate) |
| 11-18 10:42 | DOGE/USD | C-H1-tweezer-top | 3/5 | 0.05938447 | 0.05993881 | 0.05855297 | $50.00 | not fired (guard/duplicate) |
| 11-18 10:42 | SOL/USD | C-M15-tweezer-top | 3/5 | 74.866733 | 75.398168 | 74.069581 | $50.00 | not fired (guard/duplicate) |
| 11-18 10:42 | XRP/USD | C-H1-tweezer-top | 3/5 | 0.99557137 | 1.0099716 | 0.97397109 | $50.00 | not fired (guard/duplicate) |
| 11-18 10:42 | XRP/USD | S23-upthrust-short | 4/5 | 0.99557137 | 1.0099716 | 0.9735597 | $50.00 | not fired (guard/duplicate) |
| 11-18 10:42 | ETH/USD | C-M15-three-outside-down | 4/5 | 1807.651 | 1816.9975 | 1793.6311 | $50.00 | not fired (guard/duplicate) |
| 11-18 10:42 | ETH/USD | C-M15-tweezer-top | 4/5 | 1807.651 | 1816.9975 | 1793.6311 | $50.00 | not fired (guard/duplicate) |
| 11-18 03:46 | DOGE/USD | C-M15-bear-harami | 3/5 | 0.05910366 | 0.05951586 | 0.05848536 | $50.00 | not fired (guard/duplicate) |

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
