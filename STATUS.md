# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-14 15:47 UTC** · venue `shadow-ledger(coinbase-no-key)` → shadow book (paper) · cash $89,777.07 · equity $99,972.82

## Orders resting on the book now (2)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| SOL/USD | buy_stop | 76.06679 | 96.9287 | $7,373 | $75.00 | 73.89 | +2.95% | 144 min |
| XRP/USD | buy_stop | 0.99525853 | 6634.32 | $6,603 | $75.00 | 0.9723 | +2.36% | 144 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (1)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| AVAX/USD | 1326.36 | 7.641 | 7.687 | $61.01 | 7.5876058 | 8.10135 | +0.61R |

## Last 12 signals (29 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-14 15:29 | AVAX/USD | S11-dc55-short | 4/5 | 7.9267676 | 8.0053942 | 7.6908879 | $100.00 | paper-graded (spot cannot short) |
| 11-14 15:29 | AVAX/USD | S11-dc20-short | 4/5 | 7.9267676 | 8.0053942 | 7.6908879 | $100.00 | paper-graded (spot cannot short) |
| 11-14 15:29 | AVAX/USD | S4-band-fade-long | 4/5 | 7.7727869 | 7.5876058 | 8.10135 | $100.00 | order placed |
| 11-14 15:29 | LTC/USD | S11-dc55-short | 4/5 | 47.598921 | 48.012476 | 46.358255 | $100.00 | paper-graded (spot cannot short) |
| 11-14 15:29 | DOGE/USD | S4-band-fade-long | 4/5 | 0.06128356 | 0.06080355 | 0.0634155 | $100.00 | order placed |
| 11-14 14:53 | LTC/USD | S11-dc20-short | 4/5 | 47.898299 | 48.274205 | 46.770583 | $100.00 | paper-graded (spot cannot short) |
| 11-14 14:53 | ADA/USD | S11-dc55-short | 4/5 | 0.16170003 | 0.16302984 | 0.15771059 | $100.00 | paper-graded (spot cannot short) |
| 11-14 14:53 | ADA/USD | S11-dc20-short | 4/5 | 0.16170003 | 0.16302984 | 0.15771059 | $100.00 | paper-graded (spot cannot short) |
| 11-14 14:53 | DOGE/USD | C-H1-three-outside-down | 4/5 | 0.06250046 | 0.06337386 | 0.06119036 | $100.00 | paper-graded (spot cannot short) |
| 11-14 14:53 | DOGE/USD | C-H1-bear-engulfing | 4/5 | 0.06250046 | 0.06337386 | 0.06119036 | $100.00 | paper-graded (spot cannot short) |
| 11-14 14:53 | ETH/USD | C-H1-three-outside-down | 5/5 | 1893.6322 | 1914.7395 | 1861.9713 | $125.00 | paper-graded (spot cannot short) |
| 11-14 13:34 | LTC/USD | C-M15-three-crows | 5/5 | 47.577631 | 47.995922 | 46.950196 | $125.00 | paper-graded (spot cannot short) |

## Accuracy so far

0 graded outcomes · win rate 0% · avg +0.00R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 0 new order(s), 10 symbols scanned

| line starts with | meaning |
|---|---|
| `CANDIDATE(score n/5)` | a skill matched and was scored, but no order was sent (short on spot, duplicate, below the fire floor) |
| `ORDER SENT` | an order was placed on the venue named in the summary line |
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

_On a live venue the exchange is the authority: the orders above are what Sentry believes it placed, the Coinbase app's Orders/History tab is what actually exists._
