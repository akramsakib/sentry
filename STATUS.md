# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-16 17:01 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $58,958.74 · equity $100,074.68

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$87.49 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (5)

| symbol | order | trigger | size | notional | risk | tape | to trigger | age |
|---|---|---|---|---|---|---|---|---|
| ETH/USD | buy_stop | 1834.3258 | 2.9177 | $5,352 | $75.00 | 1827.84 | +0.35% | 0 min |
| LINK/USD | buy_stop | 9.2056144 | 550.862 | $5,071 | $75.00 | 9.208 | -0.03% | 0 min |
| LTC/USD | buy_stop | 44.87603 | 65.4391 | $2,937 | $75.00 | 44.82 | +0.13% | 0 min |
| SOL/USD | buy_stop | 71.398586 | 54.3458 | $3,880 | $75.00 | 71.33 | +0.10% | 0 min |
| XRP/USD | buy_stop | 0.95972892 | 4643.61 | $4,457 | $75.00 | 0.9599 | -0.02% | 0 min |

_Entries expire after 6 h (`pending_ttl_h`): a breakout trigger from 6 hours ago is not the same trade, it is just an old order._

## Positions (1)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BTC/USD | 0.069084 | 63278.87 | 64870.94 | $109.99 | 63069.244 | 66371.462 | +2.20R |

## Last 12 signals (213 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-16 17:01 | AVAX/USD | C-M15-bear-harami | 4/5 | 7.1028111 | 7.1859722 | 6.9780696 | $100.00 | paper-graded (spot cannot short) |
| 11-16 17:01 | AVAX/USD | C-M15-tweezer-top | 4/5 | 7.1028111 | 7.1859722 | 6.9780696 | $100.00 | paper-graded (spot cannot short) |
| 11-16 17:01 | AVAX/USD | C-H1-bear-engulfing | 5/5 | 7.0088111 | 7.2389722 | 6.6635696 | $125.00 | paper-graded (spot cannot short) |
| 11-16 17:01 | AVAX/USD | S16-inside-short | 4/5 | 7.0538111 | 7.1889722 | 6.897167 | $100.00 | paper-graded (spot cannot short) |
| 11-16 17:01 | BCH/USD | C-M15-bear-harami | 4/5 | 205.61064 | 207.37339 | 202.96652 | $100.00 | paper-graded (spot cannot short) |
| 11-16 17:01 | BCH/USD | S16-inside-short | 4/5 | 204.85064 | 207.54339 | 201.07965 | $100.00 | paper-graded (spot cannot short) |
| 11-16 17:01 | LTC/USD | C-M15-bear-harami | 4/5 | 44.43397 | 44.850074 | 43.809815 | $100.00 | paper-graded (spot cannot short) |
| 11-16 17:01 | LTC/USD | C-M15-tweezer-top | 4/5 | 44.43397 | 44.850074 | 43.809815 | $100.00 | paper-graded (spot cannot short) |
| 11-16 17:01 | LTC/USD | S23-spring-long | 3/5 | 44.87603 | 43.729926 | 46.653766 | $75.00 | order placed |
| 11-16 17:01 | LINK/USD | C-M15-bear-harami | 4/5 | 9.1223856 | 9.2125359 | 8.9871603 | $100.00 | paper-graded (spot cannot short) |
| 11-16 17:01 | LINK/USD | S16-inside-short | 4/5 | 9.0883856 | 9.2245359 | 8.9117846 | $100.00 | paper-graded (spot cannot short) |
| 11-16 17:01 | LINK/USD | S16-inside-long | 3/5 | 9.2056144 | 9.0694641 | 9.3822154 | $75.00 | order placed |

## Accuracy so far

1 graded outcomes (0 win / 1 loss) · win rate 0% · avg -0.61R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

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
