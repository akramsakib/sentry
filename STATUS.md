# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-20 05:29 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $45,977.44 · equity $97,818.58

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$212.48 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (5)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_stop | 61625.692 | 0.181062 | $11,158 | $75.00 | 61605.4 | +0.03% | 0 min |
| DOGE/USD | buy_stop | 0.05703304 | 130288 | $7,431 | $75.00 | 0.05696 | +0.13% | 0 min |
| LTC/USD | buy_limit | 41.35 | 107.785 | $4,457 | $56.00 | 41.37 | -0.05% | 0 min |
| LTC/USD | buy_stop | 41.491955 | 191.403 | $7,942 | $75.00 | 41.37 | +0.29% | 0 min |
| SOL/USD | buy_stop | 72.318781 | 119.859 | $8,668 | $75.00 | 72.07 | +0.35% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (1)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| XRP/USD | 4643.61 | 0.95972892 | 0.9653 | $25.87 | 0.94357771 | 0.97833374 | +0.34R |

## Last 12 signals (497 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-20 05:29 | AVAX/USD | S21-pivot-S1-short | 4/5 | 6.9207825 | 7.1086667 | 6.5736667 | $100.00 | paper-graded (spot cannot short) |
| 11-20 05:29 | AVAX/USD | S13-ichimoku-short | 4/5 | 6.8366738 | 7.0306524 | 6.6408822 | $100.00 | paper-graded (spot cannot short) |
| 11-20 05:29 | AVAX/USD | S18-rsi2-short | 4/5 | 6.851 | 6.9656097 | 6.7077379 | $100.00 | paper-graded (spot cannot short) |
| 11-20 05:29 | BCH/USD | S21-pivot-S1-short | 4/5 | 203.12636 | 208.58 | 193.01 | $100.00 | paper-graded (spot cannot short) |
| 11-20 05:29 | BCH/USD | S2-breakdown-short | 4/5 | 201.96091 | 208.41909 | 192.27365 | $100.00 | paper-graded (spot cannot short) |
| 11-20 05:29 | LTC/USD | C-H1-bear-harami | 4/5 | 41.608045 | 42.329888 | 40.525279 | $100.00 | paper-graded (spot cannot short) |
| 11-20 05:29 | LTC/USD | C-H1-tweezer-top | 4/5 | 41.608045 | 42.329888 | 40.525279 | $100.00 | paper-graded (spot cannot short) |
| 11-20 05:29 | LTC/USD | S22-rsi-bull-div | 3/5 | 41.491955 | 41.100112 | 42.079721 | $75.00 | order placed |
| 11-20 05:29 | LTC/USD | S13-ichimoku-short | 4/5 | 41.272067 | 43.220866 | 40.206983 | $100.00 | paper-graded (spot cannot short) |
| 11-20 05:29 | LTC/USD | S18-ma-revert-long | 3/5 | 41.35 | 40.830447 | 42.685954 | $56.00 | order placed |
| 11-20 05:29 | LINK/USD | S21-pivot-S1-short | 4/5 | 8.8804066 | 9.1336667 | 8.4096667 | $100.00 | paper-graded (spot cannot short) |
| 11-20 05:29 | LINK/USD | S13-ichimoku-short | 4/5 | 8.7731099 | 9.0632802 | 8.5286117 | $100.00 | paper-graded (spot cannot short) |

## Accuracy so far

13 graded outcomes (4 win / 8 loss / 1 scratch) · win rate 33% · avg -0.08R · sizing today: score 3 -> $88.00 · score 4 -> $117.00 · score 5 -> $146.00

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
