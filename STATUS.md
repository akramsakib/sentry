# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-15 23:18 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $82,783.16 · equity $100,019.94

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$68.88 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (5)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| ADA/USD | buy_stop | 0.15461567 | 39845.4 | $6,161 | $50.00 | 0.1543 | +0.20% | 0 min |
| SOL/USD | buy_stop | 72.502469 | 80.8224 | $5,860 | $50.00 | 72.25 | +0.35% | 0 min |
| XRP/USD | buy_stop | 0.97241893 | 1222.29 | $1,189 | $50.00 | 0.9704 | +0.21% | 0 min |
| XRP/USD | buy_stop | 0.97184595 | 6484.39 | $6,302 | $50.00 | 0.9704 | +0.15% | 0 min |
| XRP/USD | buy_stop | 0.97184595 | 6484.39 | $6,302 | $50.00 | 0.9704 | +0.15% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (1)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BTC/USD | 0.069084 | 63278.87 | 64877.89 | $110.47 | 63069.244 | 66371.462 | +2.21R |

## Last 12 signals (139 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-15 23:18 | LTC/USD | C-H1-tweezer-top | 4/5 | 45.104835 | 45.627913 | 44.320217 | $50.00 | paper-graded (spot cannot short) |
| 11-15 23:18 | LTC/USD | C-H1-bear-engulfing | 4/5 | 45.104835 | 45.627913 | 44.320217 | $50.00 | paper-graded (spot cannot short) |
| 11-15 23:18 | LINK/USD | C-M15-evening-star | 5/5 | 9.2370168 | 9.3059581 | 9.1336048 | $62.00 | paper-graded (spot cannot short) |
| 11-15 23:18 | LINK/USD | S22-rsi-bear-div | 4/5 | 9.2370168 | 9.3039581 | 9.1366048 | $50.00 | paper-graded (spot cannot short) |
| 11-15 23:18 | ADA/USD | C-M15-tweezer-bottom | 3/5 | 0.15461567 | 0.15336082 | 0.15649794 | $50.00 | order placed |
| 11-15 23:18 | ADA/USD | C-H1-evening-star | 4/5 | 0.15288433 | 0.15533918 | 0.14920206 | $50.00 | paper-graded (spot cannot short) |
| 11-15 23:18 | SOL/USD | C-M15-three-outside-up | 3/5 | 72.502469 | 71.883828 | 73.43043 | $50.00 | order placed |
| 11-15 23:18 | XRP/USD | C-M15-tweezer-bottom | 3/5 | 0.97184595 | 0.96413512 | 0.9834122 | $50.00 | order placed |
| 11-15 23:18 | XRP/USD | C-M15-bull-engulfing | 3/5 | 0.97184595 | 0.96413512 | 0.9834122 | $50.00 | order placed |
| 11-15 23:18 | XRP/USD | S13-ichimoku-long | 3/5 | 0.97241893 | 0.93151214 | 1.000011 | $50.00 | order placed |
| 11-15 23:18 | ETH/USD | C-H1-evening-star | 4/5 | 1810.671 | 1832.1725 | 1778.4188 | $50.00 | paper-graded (spot cannot short) |
| 11-15 23:18 | BTC/USD | C-M15-three-outside-up | 3/5 | 65268.231 | 64906.173 | 65811.317 | $50.00 | not fired (guard/duplicate) |

## Accuracy so far

1 graded outcomes (0 win / 1 loss) · win rate 0% · avg -0.61R · sizing today: score 3 -> $50.00 · score 4 -> $50.00 · score 5 -> $62.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 5 new order(s), 10 symbols scanned

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
