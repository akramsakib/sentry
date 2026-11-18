# Sentry — live status

_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees with `journal.md`, the journal is right._

**2026-11-18 02:38 UTC** · venue `shadow-ledger(okx-no-key)` → shadow book (paper) · cash $58,427.35 · equity $99,768.05

_Venue cost: 0.02 % maker / 0.05 % taker per side · **$129.07 paid on this book to date** · every graded R is net of it · live orders refused when the fee costs more than 0.25R of the trade's own risk_

## Orders resting on the book now (0)

_None. Every symbol is scanned each cycle; a resting entry above is a trigger waiting to be hit, not a position._

## Positions (6)

| symbol | qty | entry | mark | P&L | stop | target | R held |
|---|---|---|---|---|---|---|---|
| ADA/USD | 20659.4 | 0.15347 | 0.15273 | $-15.29 | 0.1510798 | 0.15652524 | -0.31R |
| BTC/USD | 0.0909312 | 64180 | 64392.04 | $19.28 | 63355.2 | 65042.397 | +0.26R |
| DOGE/USD | 54931.8 | 0.05911149 | 0.05929 | $9.81 | 0.05820127 | 0.06047682 | +0.20R |
| ETH/USD | 2.07483 | 1800.05 | 1805.24 | $10.77 | 1775.9517 | 1813.9158 | +0.22R |
| SOL/USD | 54.3458 | 71.398586 | 74.55 | $171.27 | 70.018534 | 72.918795 | +2.28R |
| XRP/USD | 4643.61 | 0.95972892 | 0.9751 | $71.38 | 0.94357771 | 0.97833374 | +0.95R |

## Last 12 signals (345 ever logged)

| time | symbol | skill | score | entry | stop | target | size | outcome |
|---|---|---|---|---|---|---|---|---|
| 11-18 02:38 | AVAX/USD | C-H1-bear-harami | 5/5 | 7.2333954 | 7.3190114 | 7.1049716 | $62.00 | paper-graded (spot cannot short) |
| 11-18 02:38 | AVAX/USD | C-H1-marubozu | 5/5 | 7.2333954 | 7.3190114 | 7.1049716 | $62.00 | paper-graded (spot cannot short) |
| 11-18 02:38 | BCH/USD | C-H1-bear-harami | 4/5 | 210.58099 | 212.94754 | 207.03116 | $50.00 | paper-graded (spot cannot short) |
| 11-18 02:38 | BCH/USD | C-H1-marubozu | 4/5 | 210.58099 | 212.94754 | 207.03116 | $50.00 | paper-graded (spot cannot short) |
| 11-18 02:38 | LTC/USD | C-H1-tweezer-top | 4/5 | 44.663199 | 45.457002 | 43.472495 | $50.00 | paper-graded (spot cannot short) |
| 11-18 02:38 | LTC/USD | C-H1-marubozu | 4/5 | 44.663199 | 45.457002 | 43.472495 | $50.00 | paper-graded (spot cannot short) |
| 11-18 02:38 | LINK/USD | C-H1-marubozu | 5/5 | 9.2316333 | 9.3504168 | 9.0534579 | $62.00 | paper-graded (spot cannot short) |
| 11-18 02:38 | ADA/USD | C-H1-marubozu | 5/5 | 0.15370354 | 0.15579116 | 0.15057211 | $62.00 | not fired (guard/duplicate) |
| 11-18 02:38 | DOGE/USD | C-H1-marubozu | 5/5 | 0.05963248 | 0.06026881 | 0.05867798 | $62.00 | not fired (guard/duplicate) |
| 11-18 02:38 | DOGE/USD | S13-ichimoku-long | 3/5 | 0.05940128 | 0.05869743 | 0.0607855 | $50.00 | not fired (guard/duplicate) |
| 11-18 02:38 | SOL/USD | S13-ichimoku-long | 3/5 | 74.66824 | 73.048519 | 76.69419 | $50.00 | not fired (guard/duplicate) |
| 11-18 02:38 | XRP/USD | S13-ichimoku-long | 3/5 | 0.97660397 | 0.96474205 | 0.99852497 | $50.00 | not fired (guard/duplicate) |

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
