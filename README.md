# Sentry v4 — GitHub-native trading brain (no MT5, no Mac, no Wine)

The same checklist engine from the Mac build (`sentry_mac.py` v3.1) ported to run entirely on
**GitHub Actions** against **Alpaca paper trading** (crypto 24/7/365 — including weekends, which
MT5 demo accounts don't offer). One workflow run = one full scan cycle, scheduled every 10 min.

```
┌─ Actions cron (*/10) ─┐   ┌─ this repo = the database ──────────┐
│ run_cycle.py          │──▶│ state.json       (orders/positions) │
│  1. fetch klines      │   │ journal.md       (every decision)   │
│  2. reconcile fills   │   │ trades_log.jsonl (accuracy → sizing)│
│  3. evaluate skills   │   └──────────────────────────────────────┘
│  4. size + fire       │──▶ Alpaca paper API (REST, keys in Secrets)
│  5. commit memory     │
└───────────────────────┘
```

- `sentry_core.py` — pure brain: EMA/RSI/ATR/Bollinger/pivots, playbook §12 candle engine,
  skill checklists S1/S2/S4/S18/S11, 5-point scoring, accuracy-based self-sizing ($50–$200).
- `broker.py` — Alpaca REST client, stdlib-only (no pip installs that can rot).
- `run_cycle.py` — orchestrator + state machine + **loud-death guards** (exits red on stale or
  thin data, never "scan ok" on nothing).
- `config.json` — symbols (top-10 crypto USDT-style `XXX/USD`), caps, min score.

## Execution modes
- **`ledger` (default, zero accounts):** real Coinbase public candles, simulated fills in
  `ledger.json`. Nothing to sign up for; works from GitHub Actions with only a GitHub repo.
- **`alpaca`:** real paper-trading venue (resting orders on their engine). Needs the two Secrets +
  flipping `config.json` → `"execution": "alpaca"`. The brain is identical; only the venue changes.

## Setup (~15 min)
1. **Alpaca (optional for now):** sign up at alpaca.markets → Home → **Paper Trading** → generate API keys (free, no KYC for paper).
2. **GitHub**: create a repo. Make it **public** if you want unlimited Actions minutes (private
   free-tier repos get 2,000 min/month; this bot uses ~6,500 at 10-min cadence). No secrets in
   the repo — only in Actions Secrets, and logic is safe to open.
3. Push everything here.
4. (Only when switching to alpaca mode) Repo → Settings → Secrets and variables → Actions → add `ALPACA_KEY_ID`, `ALPACA_SECRET`.
5. Actions tab → **sentry-cycle** → *Run workflow* once to verify, then trust the cron.

First run should end with a green check and a `scan ok · 10 symbols · …` commit landing in the repo.

## Test without any account
```
python3 run_cycle.py            # needs SENTRY_FIXTURES or keys; exits red otherwise (by design)
SENTRY_FIXTURES=/tmp/fixtures python3 run_cycle.py   # offline dry cycle, see docs/fixtures note
SENTRY_DRY=1 python3 run_cycle.py                    # real data fetch, no orders (still needs no keys? no — keys only for trading; data endpoint needs a key too, so use fixtures for zero-key tests)
```

## Honest limitations (read before calling it "the same thing")
- **Long-only execution.** Alpaca crypto spot can't short, so sell signals are *paper-graded*
  into the accuracy loop (they still earn the sizing trust but never fire live). Futures or a
  different venue would be needed for real shorts.
- **Stop-loss/TP enforcement is hybrid**: a server-side stop order is armed per position, but
  take-profit and breakeven/trailing moves are enforced per cycle — up to ~10 min of reaction
  latency (cron jitter included). Fine at M15 demo cadence; not scalping.
- **Cron is best-effort**: Actions schedules can lag minutes or occasionally skip under load; the
  design is stateless-per-cycle so a missed run just delays the next reconcile — but know it.
- **Paper fills ≠ real books**: Alpaca paper simulates against live prices; slippage/liquidity
  on thin weekend alts will be optimistic.
- Outcome grading for closed trades uses the last tracked price vs tp/sl (heuristic), not the
  exchange fill report — win/loss flags can be ±1 grade off on violent bars.
- FX & US equities stay on the Mac/MT5 build (OANDA practice API is the natural adapter if you
  ever want forex here too — it's one `broker_oanda.py` away).

## Why this design survives what the Mac version suffered
| Failure mode | Mac build | v4 here |
|---|---|---|
| bridge/terminal down | cycles silently with empty quotes | job exits **red** → GitHub notification |
| stale candle window (hardcoded dates) | would trade blind | staleness guard: >3h-old bar = ALERT |
| JSON quoted through bash | `-32700` spam, 177× | stdlib REST client, no shell at all |
| broker renames a symbol | hardcoded dict breaks | adapter + config, catalog-free spot pairs |
| state lost | Mac-local file | state lives in git history, diffable forever |
