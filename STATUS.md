# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-17 20:44 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $71,175.09 · equity $99,563.61

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$122.70 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (2)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_stop | 64180 | 0.0909312 | $5,836 | $75.00 | 63958.2 | +0.35% | 171 min |
| ETH/USD | buy_stop | 1800.05 | 2.07483 | $3,735 | $50.00 | 1797.85 | +0.12% | 136 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (3)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| DOGE/USD | 54931.8 | 0.05911149 | 0.05933 | $12.00 | 0.05820127 | 0.06047682 | +0.24R |
| SOL/USD | 54.3458 | 71.398586 | 72.98 | $85.94 | 70.018534 | 72.918795 | +1.15R |
| XRP/USD | 4643.61 | 0.95972892 | 0.9677 | $37.01 | 0.94357771 | 0.97833374 | +0.49R |

## Last 12 signals (321 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-17 20:44 | LINK/USD | C-M15-tweezer-top | 4/5 | 9.0677326 | 9.1451685 | 8.9515787 | $50.00 | paper-graded (spot cannot short) |
| 11-17 20:44 | DOGE/USD | C-M15-tweezer-top | 4/5 | 0.05877984 | 0.05925541 | 0.05806648 | $50.00 | not fired (guard/duplicate) |
| 11-17 20:20 | AVAX/USD | C-H1-tweezer-top | 4/5 | 7.0410079 | 7.1629803 | 6.8580493 | $50.00 | paper-graded (spot cannot short) |
| 11-17 20:20 | LINK/USD | S18-rsi2-short | 4/5 | 9.125 | 9.2602088 | 8.955989 | $50.00 | paper-graded (spot cannot short) |
| 11-17 20:20 | ADA/USD | C-H1-bear-harami | 4/5 | 0.15089665 | 0.15340838 | 0.14712906 | $50.00 | paper-graded (spot cannot short) |
| 11-17 20:20 | ADA/USD | C-H1-tweezer-top | 4/5 | 0.15089665 | 0.15340838 | 0.14712906 | $50.00 | paper-graded (spot cannot short) |
| 11-17 18:56 | DOGE/USD | C-M15-bull-engulfing | 4/5 | 0.05911149 | 0.05820127 | 0.06047682 | $50.00 | order placed |
| 11-17 18:56 | SOL/USD | C-M15-three-inside-up | 4/5 | 73.032794 | 71.743016 | 74.96746 | $50.00 | not fired (guard/duplicate) |
| 11-17 18:56 | SOL/USD | C-M15-tweezer-bottom | 4/5 | 73.032794 | 71.743016 | 74.96746 | $50.00 | not fired (guard/duplicate) |
| 11-17 18:56 | XRP/USD | C-M15-three-inside-up | 4/5 | 0.9644382 | 0.95065449 | 0.98511378 | $50.00 | not fired (guard/duplicate) |
| 11-17 18:56 | XRP/USD | C-M15-bull-engulfing | 4/5 | 0.9644382 | 0.95065449 | 0.98511378 | $50.00 | not fired (guard/duplicate) |
| 11-17 18:28 | BCH/USD | C-M15-three-outside-down | 4/5 | 206.56396 | 208.30509 | 203.95227 | $50.00 | paper-graded (spot cannot short) |

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
