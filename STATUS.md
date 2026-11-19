# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-19 17:43 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $42,358.52 · equity $99,155.88

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$187.96 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (2)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| LTC/USD | buy_limit | 42.91 | 198.317 | $8,510 | $50.00 | 42.9 | +0.02% | 0 min |
| LTC/USD | buy_limit | 42.91 | 118.99 | $5,106 | $50.00 | 42.9 | +0.02% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (3)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| DOGE/USD | 157867 | 0.05807 | 0.0589 | $131.03 | 0.05790527 | 0.0593965 | +2.34R |
| SOL/USD | 108.486 | 72.53 | 73.97 | $156.22 | 72.273804 | 74.428 | +2.79R |
| XRP/USD | 4643.61 | 0.95972892 | 0.9735 | $63.95 | 0.94357771 | 0.97833374 | +0.85R |

## Last 12 signals (452 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-19 17:43 | BCH/USD | S22-rsi-bear-div | 4/5 | 203.62878 | 210.52804 | 193.27989 | $50.00 | paper-graded (spot cannot short) |
| 11-19 17:43 | LTC/USD | C-M15-marubozu | 4/5 | 42.43798 | 43.165051 | 41.347373 | $50.00 | paper-graded (spot cannot short) |
| 11-19 17:43 | LTC/USD | S18-ma-revert-long | 3/5 | 42.91 | 42.489796 | 44.146965 | $50.00 | order placed |
| 11-19 17:43 | LTC/USD | S4-band-fade-long | 3/5 | 43.256573 | 42.657878 | 44.203 | $50.00 | order placed |
| 11-19 17:43 | DOGE/USD | S10-ma-cross-short | 4/5 | 0.05871878 | 0.05956732 | 0.05738536 | $50.00 | not fired (guard/duplicate) |
| 11-19 08:45 | LINK/USD | C-M15-evening-star | 5/5 | 9.1327594 | 9.1971015 | 9.0362461 | $62.00 | paper-graded (spot cannot short) |
| 11-19 08:45 | DOGE/USD | C-H1-three-outside-up | 3/5 | 0.05949835 | 0.05892411 | 0.06035972 | $50.00 | not fired (guard/duplicate) |
| 11-19 08:45 | SOL/USD | C-H1-marubozu | 4/5 | 75.199696 | 74.390759 | 76.413101 | $50.00 | not fired (guard/duplicate) |
| 11-19 08:45 | XRP/USD | C-H1-three-outside-up | 4/5 | 0.98483003 | 0.97052492 | 1.0062877 | $50.00 | not fired (guard/duplicate) |
| 11-19 08:45 | ETH/USD | C-M15-tweezer-top | 3/5 | 1799.5223 | 1810.9143 | 1782.4342 | $50.00 | paper-graded (spot cannot short) |
| 11-19 08:45 | ETH/USD | C-M15-bear-engulfing | 3/5 | 1799.5223 | 1810.9143 | 1782.4342 | $50.00 | paper-graded (spot cannot short) |
| 11-19 08:45 | ETH/USD | S22-rsi-bear-div | 4/5 | 1799.5223 | 1815.1443 | 1776.0892 | $50.00 | paper-graded (spot cannot short) |

## Accuracy so far

11 graded outcomes (2 win / 8 loss / 1 scratch) · win rate 20% · avg -0.37R · sizing today: score 3 -> $50.00 · score 4 -> $50.00 · score 5 -> $62.00

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
