# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-18 16:34 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $67,256.47 · equity $98,993.57

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$171.41 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (4)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BCH/USD | buy_stop | 207.43764 | 27.4278 | $5,690 | $56.00 | 205.44 | +0.97% | 0 min |
| DOGE/USD | buy_limit | 0.05826 | 157867 | $9,197 | $56.00 | 0.05826 | +0.00% | 0 min |
| ETH/USD | buy_stop | 1778.1605 | 1.77043 | $3,148 | $50.00 | 1753.61 | +1.40% | 65 min |
| SOL/USD | buy_limit | 72.79 | 108.486 | $7,897 | $56.00 | 72.79 | +0.00% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (2)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BTC/USD | 0.257612 | 62879.25 | 62448.76 | $-110.90 | 62742.065 | 64364.375 | -1.48R |
| XRP/USD | 4643.61 | 0.95972892 | 0.9688 | $42.12 | 0.94357771 | 0.97833374 | +0.56R |

## Last 12 signals (414 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-18 16:34 | BCH/USD | S16-inside-short | 4/5 | 205.69236 | 207.73409 | 202.92546 | $75.00 | paper-graded (spot cannot short) |
| 11-18 16:34 | BCH/USD | S16-inside-long | 3/5 | 207.43764 | 205.39591 | 210.20454 | $56.00 | order placed |
| 11-18 16:34 | LTC/USD | S21-pivot-S1-short | 4/5 | 43.571116 | 44.626667 | 41.586667 | $75.00 | paper-graded (spot cannot short) |
| 11-18 16:34 | DOGE/USD | S4-band-fade-long | 3/5 | 0.05882026 | 0.05790527 | 0.0593965 | $56.00 | order placed |
| 11-18 16:34 | SOL/USD | S4-band-fade-long | 3/5 | 73.260771 | 72.273804 | 74.428 | $56.00 | order placed |
| 11-18 16:34 | BTC/USD | C-M15-three-crows | 4/5 | 62683.413 | 63236.818 | 61853.304 | $75.00 | not fired (guard/duplicate) |
| 11-18 16:34 | BTC/USD | C-M15-marubozu | 4/5 | 62683.413 | 63236.818 | 61853.304 | $75.00 | not fired (guard/duplicate) |
| 11-18 16:11 | BTC/USD | S13-ichimoku-short | 4/5 | 62943.069 | 64384.862 | 61887.577 | $75.00 | not fired (guard/duplicate) |
| 11-18 16:03 | AVAX/USD | C-M15-three-outside-down | 4/5 | 6.9483291 | 7.0646773 | 6.7738068 | $67.00 | paper-graded (spot cannot short) |
| 11-18 16:03 | AVAX/USD | C-M15-tweezer-top | 4/5 | 6.9483291 | 7.0646773 | 6.7738068 | $67.00 | paper-graded (spot cannot short) |
| 11-18 16:03 | AVAX/USD | C-M15-bear-engulfing | 4/5 | 6.9483291 | 7.0646773 | 6.7738068 | $67.00 | paper-graded (spot cannot short) |
| 11-18 16:03 | AVAX/USD | S21-pivot-S1-short | 4/5 | 6.9703291 | 7.146 | 6.645 | $67.00 | paper-graded (spot cannot short) |

## Accuracy so far

10 graded outcomes (2 win / 7 loss / 1 scratch) · win rate 22% · avg -0.24R · sizing today: score 3 -> $50.00 · score 4 -> $67.00 · score 5 -> $83.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 3 new order(s), 10 symbols scanned

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
