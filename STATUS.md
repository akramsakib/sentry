# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-15 18:55 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $82,783.16 · equity $99,883.71

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$68.88 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (0)

_None. Every symbol is scanned each cycle; a resting entry above is a trigger waiting to be hit, not a position._

## Positions (1)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BTC/USD | 0.069084 | 63278.87 | 64623.45 | $92.89 | 63069.244 | 66371.462 | +1.86R |

## Last 12 signals (127 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-15 18:55 | AVAX/USD | S22-rsi-bear-div | 4/5 | 7.1398415 | 7.2563962 | 6.9650096 | $50.00 | paper-graded (spot cannot short) |
| 11-15 18:55 | BCH/USD | C-H1-bear-harami | 4/5 | 206.66423 | 210.12441 | 201.47397 | $50.00 | paper-graded (spot cannot short) |
| 11-15 18:55 | LTC/USD | C-H1-shooting-star | 4/5 | 44.625639 | 45.460903 | 43.372743 | $50.00 | paper-graded (spot cannot short) |
| 11-15 18:55 | LINK/USD | C-H1-bear-harami | 4/5 | 9.1302324 | 9.3004189 | 8.8749528 | $50.00 | paper-graded (spot cannot short) |
| 11-15 18:55 | ADA/USD | C-M15-tweezer-top | 4/5 | 0.15255333 | 0.15411667 | 0.15020833 | $50.00 | paper-graded (spot cannot short) |
| 11-15 18:55 | ADA/USD | C-M15-shooting-star | 4/5 | 0.15255333 | 0.15411667 | 0.15020833 | $50.00 | paper-graded (spot cannot short) |
| 11-15 18:55 | DOGE/USD | C-M15-gravestone | 4/5 | 0.05840123 | 0.05893192 | 0.05760519 | $50.00 | paper-graded (spot cannot short) |
| 11-15 18:55 | XRP/USD | C-H1-tweezer-top | 4/5 | 0.94617165 | 0.96372088 | 0.91984779 | $50.00 | paper-graded (spot cannot short) |
| 11-15 18:55 | XRP/USD | C-H1-bear-engulfing | 4/5 | 0.94617165 | 0.96372088 | 0.91984779 | $50.00 | paper-graded (spot cannot short) |
| 11-15 18:55 | XRP/USD | S22-rsi-bear-div | 4/5 | 0.94507165 | 0.96372088 | 0.91709779 | $50.00 | paper-graded (spot cannot short) |
| 11-15 18:55 | ETH/USD | C-M15-evening-star | 4/5 | 1807.6745 | 1825.7286 | 1780.5934 | $50.00 | paper-graded (spot cannot short) |
| 11-15 18:55 | BTC/USD | C-M15-gravestone | 4/5 | 64427.979 | 64974.953 | 63607.518 | $50.00 | not fired (guard/duplicate) |

## Accuracy so far

1 graded outcomes (0 win / 1 loss) · win rate 0% · avg -0.61R · sizing today: score 3 -> $50.00 · score 4 -> $50.00 · score 5 -> $62.00

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
