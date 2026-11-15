# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-15 12:14 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $82,783.16 · equity $100,074.16

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$68.88 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (0)

_None. Every symbol is scanned each cycle; a resting entry above is a trigger waiting to be hit, not a position._

## Positions (1)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BTC/USD | 0.069084 | 63278.87 | 65331.22 | $141.78 | 63069.244 | 66371.462 | +2.84R |

## Last 12 signals (114 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-15 12:14 | AVAX/USD | C-M15-bear-harami | 4/5 | 7.2133485 | 7.3161287 | 7.0591782 | $50.00 | paper-graded (spot cannot short) |
| 11-15 12:14 | BCH/USD | S23-upthrust-short | 4/5 | 207.56193 | 210.32518 | 203.4788 | $50.00 | paper-graded (spot cannot short) |
| 11-15 12:14 | LTC/USD | C-M15-tweezer-top | 3/5 | 45.32836 | 45.7891 | 44.637249 | $50.00 | paper-graded (spot cannot short) |
| 11-15 12:14 | ETH/USD | C-M15-tweezer-top | 4/5 | 1826.6166 | 1845.1486 | 1798.8185 | $50.00 | paper-graded (spot cannot short) |
| 11-15 12:14 | BTC/USD | C-M15-morning-star | 3/5 | 65639.894 | 65147.615 | 66378.313 | $50.00 | not fired (guard/duplicate) |
| 11-15 04:33 | LTC/USD | S18-rsi2-short | 3/5 | 44.88 | 45.942915 | 43.551356 | $50.00 | paper-graded (spot cannot short) |
| 11-15 04:33 | ETH/USD | C-M15-bull-harami | 3/5 | 1824.6496 | 1802.616 | 1857.6999 | $50.00 | order placed |
| 11-15 04:33 | ETH/USD | C-H1-three-inside-up | 3/5 | 1826.3396 | 1716.276 | 1991.4349 | $50.00 | order placed |
| 11-15 04:33 | ETH/USD | C-H1-morning-star | 3/5 | 1826.3396 | 1716.276 | 1991.4349 | $50.00 | order placed |
| 11-15 04:33 | ETH/USD | C-H1-marubozu | 3/5 | 1826.3396 | 1716.276 | 1991.4349 | $50.00 | order placed |
| 11-15 04:33 | ETH/USD | S22-rsi-bull-div | 3/5 | 1824.6496 | 1700.356 | 2011.0899 | $50.00 | order placed |
| 11-15 04:33 | BTC/USD | C-H1-three-inside-up | 3/5 | 65214.363 | 62214.743 | 69713.793 | $50.00 | not fired (guard/duplicate) |

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
