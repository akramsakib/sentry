# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-17 11:59 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $27,117.82 · equity $100,600.92

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$97.41 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (0)

_None. Every symbol is scanned each cycle; a resting entry above is a trigger waiting to be hit, not a position._

## Positions (6)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| BCH/USD | 28.7168 | 209.26724 | 211.17 | $54.64 | 206.65552 | 213.3295 | +0.73R |
| BTC/USD | 0.069084 | 63278.87 | 64922.33 | $113.54 | 63069.244 | 66371.462 | +2.27R |
| ETH/USD | 7.31746 | 1793.72 | 1820.34 | $194.79 | 1787.8905 | 1824.216 | +2.60R |
| LINK/USD | 550.862 | 9.2056144 | 9.25 | $24.45 | 9.0694641 | 9.3822154 | +0.33R |
| SOL/USD | 54.3458 | 71.398586 | 73.45 | $111.49 | 70.018534 | 72.918795 | +1.49R |
| XRP/USD | 4643.61 | 0.95972892 | 0.9701 | $48.16 | 0.94357771 | 0.97833374 | +0.64R |

## Last 12 signals (277 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-17 11:59 | BCH/USD | C-H1-tweezer-top | 3/5 | 208.18778 | 210.08055 | 205.34863 | $75.00 | not fired (guard/duplicate) |
| 11-17 11:59 | BCH/USD | S4-band-fade-short | 3/5 | 210.12545 | 212.18331 | 208.3525 | $75.00 | not fired (guard/duplicate) |
| 11-17 11:59 | LINK/USD | C-H1-hammer/takuri | 3/5 | 9.1820738 | 9.0543155 | 9.3737112 | $75.00 | not fired (guard/duplicate) |
| 11-17 11:59 | XRP/USD | S13-ichimoku-long | 3/5 | 0.97039331 | 0.95611338 | 0.98943522 | $75.00 | not fired (guard/duplicate) |
| 11-17 11:59 | ETH/USD | S13-ichimoku-short | 4/5 | 1816.3271 | 1831.7608 | 1779.7973 | $100.00 | not fired (guard/duplicate) |
| 11-17 11:59 | BTC/USD | C-H1-bull-harami | 3/5 | 64542.769 | 64035.827 | 65303.182 | $75.00 | not fired (guard/duplicate) |
| 11-17 10:59 | AVAX/USD | C-M15-evening-star | 4/5 | 7.1336534 | 7.2028664 | 7.029834 | $100.00 | paper-graded (spot cannot short) |
| 11-17 10:59 | LINK/USD | C-M15-tweezer-bottom | 3/5 | 9.1512179 | 9.0789552 | 9.259612 | $75.00 | not fired (guard/duplicate) |
| 11-17 10:59 | SOL/USD | S18-rsi2-long | 4/5 | 72.22 | 71.269289 | 73.408388 | $100.00 | not fired (guard/duplicate) |
| 11-17 10:41 | AVAX/USD | C-M15-tweezer-top | 5/5 | 7.1486534 | 7.2158664 | 7.047834 | $125.00 | paper-graded (spot cannot short) |
| 11-17 10:41 | LINK/USD | C-M15-bear-engulfing | 5/5 | 9.0997821 | 9.1860448 | 8.970388 | $125.00 | not fired (guard/duplicate) |
| 11-17 10:41 | ADA/USD | C-M15-tweezer-top | 5/5 | 0.15233285 | 0.15371787 | 0.15025531 | $125.00 | paper-graded (spot cannot short) |

## Accuracy so far

1 graded outcomes (0 win / 1 loss) · win rate 0% · avg -0.61R · sizing today: score 3 -> $75.00 · score 4 -> $100.00 · score 5 -> $125.00

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
