# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-28 13:55 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $-177,511.61 · equity $95,931.83

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$425.05 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (1)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| BTC/USD | buy_stop | 59310.039 | 0.142374 | $8,444 | $50.00 | 59011.3 | +0.51% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (5)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| DOGE/USD | 292204 | 0.05629 | 0.05625 | $-11.69 | 0.05612059 | 0.056744 | -0.16R |
| ETH/USD | 9.00073 | 1689.5815 | 1639.63 | $-449.60 | 1678.4713 | 1706.2468 | -4.50R |
| LTC/USD | 203.958 | 44.260085 | 43.718 | $-110.56 | 43.769787 | 44.995532 | -1.11R |
| SOL/USD | 89.9789 | 70.29 | 70.24 | $-4.50 | 69.188628 | 71.689215 | -0.04R |
| XRP/USD | 5578.33 | 0.9326 | 0.9348 | $12.27 | 0.92035512 | 0.95060611 | +0.16R |

## Last 12 signals (898 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-28 13:55 | BCH/USD | C-M15-three-outside-down | 4/5 | 204.30729 | 205.71677 | 202.19309 | $50.00 | paper-graded (spot cannot short) |
| 11-28 13:55 | BCH/USD | C-M15-marubozu | 4/5 | 204.30729 | 205.71677 | 202.19309 | $50.00 | paper-graded (spot cannot short) |
| 11-28 13:55 | LTC/USD | C-H1-tweezer-bottom | 3/5 | 44.098932 | 43.682669 | 44.723328 | $50.00 | not fired (guard/duplicate) |
| 11-28 13:55 | LINK/USD | C-M15-three-outside-down | 3/5 | 9.1175289 | 9.1796777 | 9.0243058 | $50.00 | paper-graded (spot cannot short) |
| 11-28 13:55 | LINK/USD | C-M15-bear-engulfing | 3/5 | 9.1175289 | 9.1796777 | 9.0243058 | $50.00 | paper-graded (spot cannot short) |
| 11-28 13:55 | DOGE/USD | S13-ichimoku-short | 4/5 | 0.05621109 | 0.05779281 | 0.05526936 | $50.00 | not fired (guard/duplicate) |
| 11-28 13:55 | DOGE/USD | S4-band-fade-long | 4/5 | 0.05638114 | 0.05600437 | 0.0573115 | $50.00 | not fired (guard/duplicate) |
| 11-28 13:55 | SOL/USD | S21-pivot-R1-long | 4/5 | 69.962713 | 67.843333 | 74.033333 | $50.00 | not fired (guard/duplicate) |
| 11-28 13:55 | XRP/USD | C-H1-tweezer-bottom | 3/5 | 0.94026457 | 0.93363857 | 0.95020359 | $50.00 | not fired (guard/duplicate) |
| 11-28 13:55 | XRP/USD | S23-spring-long | 3/5 | 0.94026457 | 0.93363857 | 0.95020161 | $50.00 | not fired (guard/duplicate) |
| 11-28 13:55 | XRP/USD | S13-ichimoku-short | 4/5 | 0.93360314 | 0.95994372 | 0.91997937 | $50.00 | not fired (guard/duplicate) |
| 11-28 13:55 | XRP/USD | S4-band-fade-long | 3/5 | 0.93741866 | 0.93061256 | 0.9462 | $50.00 | not fired (guard/duplicate) |

## Accuracy so far

15 graded outcomes (5 win / 9 loss / 1 scratch) · win rate 36% · avg -0.23R · sizing today: score 3 -> $50.00 · score 4 -> $50.00 · score 5 -> $62.00

_Risk per trade is this bot's own decision: it scales with the accuracy it has demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by `live_max_risk` on a live venue._

## This cycle: 1 new order(s), 10 symbols scanned

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
