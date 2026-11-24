# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-24 11:03 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-152,586.33 · equity $96,013.09

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$312.85 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (0)

_None. Every symbol is scanned each cycle; a resting entry above is a trigger waiting to be hit, not a position._

## Positions (0)

_Flat._

## Last 12 signals (665 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-24 11:03 | AVAX/USD | C-H1-bear-engulfing | 3/5 | 6.6707476 | 6.7586309 | 6.5389227 | $75.00 | paper-graded (spot cannot short) |
| 11-24 11:03 | AVAX/USD | S13-ichimoku-short | 4/5 | 6.6916214 | 6.9607571 | 6.5224478 | $100.00 | paper-graded (spot cannot short) |
| 11-24 11:03 | BCH/USD | S13-ichimoku-short | 4/5 | 197.32693 | 205.60613 | 192.22838 | $100.00 | paper-graded (spot cannot short) |
| 11-24 11:03 | BCH/USD | S2-breakdown-short | 4/5 | 196.25822 | 204.35178 | 184.1179 | $100.00 | paper-graded (spot cannot short) |
| 11-24 11:03 | LTC/USD | S13-ichimoku-short | 4/5 | 40.886242 | 42.197516 | 39.878216 | $100.00 | paper-graded (spot cannot short) |
| 11-24 11:03 | LINK/USD | S13-ichimoku-short | 4/5 | 8.9338825 | 9.2402349 | 8.7136103 | $100.00 | paper-graded (spot cannot short) |
| 11-24 11:03 | ADA/USD | S13-ichimoku-short | 4/5 | 0.14560913 | 0.15113174 | 0.14163388 | $100.00 | paper-graded (spot cannot short) |
| 11-24 11:03 | DOGE/USD | S13-ichimoku-short | 4/5 | 0.05547626 | 0.05794748 | 0.05405847 | $100.00 | paper-graded (spot cannot short) |
| 11-24 11:03 | SOL/USD | S13-ichimoku-short | 4/5 | 70.29167 | 74.52166 | 68.401159 | $100.00 | paper-graded (spot cannot short) |
| 11-24 11:03 | XRP/USD | S13-ichimoku-short | 4/5 | 0.92698067 | 0.98163866 | 0.90211653 | $100.00 | paper-graded (spot cannot short) |
| 11-24 11:03 | ETH/USD | S3-momentum-short | 4/5 | 1672.4621 | 1697.1257 | 1625.0928 | $100.00 | paper-graded (spot cannot short) |
| 11-24 11:03 | BTC/USD | C-M15-marubozu | 4/5 | 59592.878 | 60021.204 | 58950.389 | $100.00 | paper-graded (spot cannot short) |

## Accuracy so far

14 graded outcomes (5 win / 8 loss / 1 scratch) · win rate 38% · avg -0.05R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

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
