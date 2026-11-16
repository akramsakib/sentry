# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-16 20:39 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $45,544.19 · equity $99,713.60

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$87.49 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (2)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| ETH/USD | buy_stop | 1834.3258 | 2.9177 | $5,352 | $75.00 | 1821.04 | +0.73% | 218 min |
| LTC/USD | buy_stop | 44.87603 | 65.4391 | $2,937 | $75.00 | 44.97 | -0.21% | 218 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (4)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BTC/USD | 0.069084 | 63278.87 | 64917.25 | $113.19 | 63069.244 | 66371.462 | +2.26R |
| LINK/USD | 550.862 | 9.2056144 | 9.109 | $-53.22 | 9.0694641 | 9.3822154 | -0.71R |
| SOL/USD | 54.3458 | 71.398586 | 71.2 | $-10.79 | 70.018534 | 72.918795 | -0.14R |
| XRP/USD | 4643.61 | 0.95972892 | 0.9536 | $-28.46 | 0.94357771 | 0.97833374 | -0.38R |

## Last 12 signals (223 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-16 20:39 | LINK/USD | C-M15-shooting-star | 4/5 | 9.1790294 | 9.2499264 | 9.0726839 | $100.00 | not fired (guard/duplicate) |
| 11-16 20:39 | LINK/USD | C-H1-tweezer-bottom | 4/5 | 9.2579706 | 9.0900736 | 9.5098161 | $100.00 | not fired (guard/duplicate) |
| 11-16 20:39 | SOL/USD | C-M15-bear-harami | 4/5 | 71.309744 | 71.920639 | 70.393403 | $100.00 | not fired (guard/duplicate) |
| 11-16 20:39 | SOL/USD | C-M15-shooting-star | 4/5 | 71.309744 | 71.920639 | 70.393403 | $100.00 | not fired (guard/duplicate) |
| 11-16 20:39 | SOL/USD | C-H1-bull-engulfing | 3/5 | 71.680256 | 70.579361 | 73.331597 | $75.00 | not fired (guard/duplicate) |
| 11-16 20:39 | XRP/USD | C-M15-shooting-star | 4/5 | 0.95715179 | 0.96512053 | 0.94519868 | $100.00 | not fired (guard/duplicate) |
| 11-16 20:39 | BTC/USD | C-M15-bear-harami | 4/5 | 64933.84 | 65268.349 | 64432.076 | $100.00 | not fired (guard/duplicate) |
| 11-16 20:39 | BTC/USD | C-M15-shooting-star | 4/5 | 64933.84 | 65268.349 | 64432.076 | $100.00 | not fired (guard/duplicate) |
| 11-16 18:34 | XRP/USD | C-M15-hammer/takuri | 3/5 | 0.95840828 | 0.9494293 | 0.97187675 | $75.00 | not fired (guard/duplicate) |
| 11-16 18:34 | BTC/USD | S18-rsi2-long | 4/5 | 64793.8 | 64015.827 | 65766.267 | $100.00 | not fired (guard/duplicate) |
| 11-16 17:01 | AVAX/USD | C-M15-bear-harami | 4/5 | 7.1028111 | 7.1859722 | 6.9780696 | $100.00 | paper-graded (spot cannot short) |
| 11-16 17:01 | AVAX/USD | C-M15-tweezer-top | 4/5 | 7.1028111 | 7.1859722 | 6.9780696 | $100.00 | paper-graded (spot cannot short) |

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
