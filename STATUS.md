# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-24 21:06 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-152,586.33 · equity $93,755.66

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$312.85 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (6)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| ADA/USD | buy_stop | 0.14389525 | 54215.4 | $7,801 | $75.00 | 0.1438 | +0.07% | 0 min |
| DOGE/USD | buy_stop | 0.05521634 | 221151 | $12,211 | $100.00 | 0.05527 | -0.10% | 0 min |
| DOGE/USD | buy_stop | 0.05521634 | 221151 | $12,211 | $100.00 | 0.05527 | -0.10% | 0 min |
| LTC/USD | buy_stop | 40.822794 | 200.118 | $8,169 | $75.00 | 40.8 | +0.06% | 0 min |
| SOL/USD | buy_stop | 69.219909 | 130.507 | $9,034 | $75.00 | 69.28 | -0.09% | 0 min |
| XRP/USD | buy_stop | 0.91971303 | 10569.9 | $9,721 | $75.00 | 0.9193 | +0.04% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (0)

_Flat._

## Last 12 signals (680 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-24 21:06 | AVAX/USD | C-H1-evening-star | 3/5 | 6.5263287 | 6.6086782 | 6.4028046 | $75.00 | paper-graded (spot cannot short) |
| 11-24 21:06 | BCH/USD | S11-dc20-short | 4/5 | 194.35845 | 196.11928 | 189.07596 | $100.00 | paper-graded (spot cannot short) |
| 11-24 21:06 | LTC/USD | C-M15-bull-harami | 3/5 | 40.822794 | 40.448015 | 41.384962 | $75.00 | order placed |
| 11-24 21:06 | LTC/USD | S1-pullback-short | 4/5 | 40.920699 | 41.271985 | 40.393769 | $100.00 | paper-graded (spot cannot short) |
| 11-24 21:06 | LINK/USD | C-H1-evening-star | 5/5 | 8.8040111 | 8.9264722 | 8.6203194 | $125.00 | paper-graded (spot cannot short) |
| 11-24 21:06 | ADA/USD | C-M15-tweezer-bottom | 3/5 | 0.14389525 | 0.14251188 | 0.1459703 | $75.00 | order placed |
| 11-24 21:06 | ADA/USD | S3-momentum-short | 4/5 | 0.14350475 | 0.1455905 | 0.13952851 | $100.00 | paper-graded (spot cannot short) |
| 11-24 21:06 | DOGE/USD | C-M15-bull-harami | 4/5 | 0.05521634 | 0.05476416 | 0.05589461 | $100.00 | order placed |
| 11-24 21:06 | DOGE/USD | C-M15-tweezer-bottom | 4/5 | 0.05521634 | 0.05476416 | 0.05589461 | $100.00 | order placed |
| 11-24 21:06 | DOGE/USD | S1-pullback-short | 4/5 | 0.05557578 | 0.05569584 | 0.05539568 | $100.00 | paper-graded (spot cannot short) |
| 11-24 21:06 | SOL/USD | C-M15-tweezer-bottom | 3/5 | 69.219909 | 68.645228 | 70.081929 | $75.00 | order placed |
| 11-24 21:06 | XRP/USD | C-M15-tweezer-bottom | 3/5 | 0.91971303 | 0.91261742 | 0.93035645 | $75.00 | order placed |

## Accuracy so far

14 graded outcomes (5 win / 8 loss / 1 scratch) · win rate 38% · avg -0.05R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 6 new order(s), 10 symbols scanned

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
