# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-17 22:27 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $58,427.35 · equity $99,697.76

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$129.07 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (0)

_None. Every symbol is scanned each cycle; a resting entry above is a trigger waiting to be hit, not a position._

## Positions (6)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| ADA/USD | 20659.4 | 0.15347 | 0.15408 | $12.60 | 0.1510798 | 0.15652524 | +0.25R |
| BTC/USD | 0.0909312 | 64180 | 64488.47 | $28.05 | 63355.2 | 65042.397 | +0.37R |
| DOGE/USD | 54931.8 | 0.05911149 | 0.0594 | $15.85 | 0.05820127 | 0.06047682 | +0.32R |
| ETH/USD | 2.07483 | 1800.05 | 1805.4 | $11.10 | 1775.9517 | 1813.9158 | +0.22R |
| SOL/USD | 54.3458 | 71.398586 | 73.64 | $121.81 | 70.018534 | 72.918795 | +1.62R |
| XRP/USD | 4643.61 | 0.95972892 | 0.9694 | $44.91 | 0.94357771 | 0.97833374 | +0.60R |

## Last 12 signals (330 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-17 22:03 | BTC/USD | C-H1-morning-star | 3/5 | 64127.145 | 63504.388 | 65061.281 | $50.00 | not fired (guard/duplicate) |
| 11-17 22:03 | BTC/USD | C-H1-tweezer-bottom | 3/5 | 64127.145 | 63504.388 | 65061.281 | $50.00 | not fired (guard/duplicate) |
| 11-17 21:59 | ADA/USD | S18-rsi2-long | 4/5 | 0.1535 | 0.1510798 | 0.15652524 | $50.00 | order placed |
| 11-17 21:59 | DOGE/USD | C-M15-three-outside-up | 4/5 | 0.05975965 | 0.05895587 | 0.06096533 | $50.00 | not fired (guard/duplicate) |
| 11-17 21:59 | DOGE/USD | S18-rsi2-long | 4/5 | 0.05927 | 0.05843418 | 0.06031478 | $50.00 | not fired (guard/duplicate) |
| 11-17 21:59 | XRP/USD | C-H1-three-outside-up | 4/5 | 0.9678133 | 0.95311675 | 0.98985812 | $50.00 | not fired (guard/duplicate) |
| 11-17 21:59 | XRP/USD | S18-rsi2-long | 4/5 | 0.9689 | 0.9555404 | 0.9855995 | $50.00 | not fired (guard/duplicate) |
| 11-17 21:59 | ETH/USD | C-M15-three-outside-up | 4/5 | 1813.2437 | 1790.7856 | 1846.9309 | $50.00 | not fired (guard/duplicate) |
| 11-17 21:59 | ETH/USD | C-M15-tweezer-bottom | 4/5 | 1813.2437 | 1790.7856 | 1846.9309 | $50.00 | not fired (guard/duplicate) |
| 11-17 20:44 | LINK/USD | C-M15-tweezer-top | 4/5 | 9.0677326 | 9.1451685 | 8.9515787 | $50.00 | paper-graded (spot cannot short) |
| 11-17 20:44 | DOGE/USD | C-M15-tweezer-top | 4/5 | 0.05877984 | 0.05925541 | 0.05806648 | $50.00 | not fired (guard/duplicate) |
| 11-17 20:20 | AVAX/USD | C-H1-tweezer-top | 4/5 | 7.0410079 | 7.1629803 | 6.8580493 | $50.00 | paper-graded (spot cannot short) |

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
