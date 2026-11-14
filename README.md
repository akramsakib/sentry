# Sentry v4 — GitHub-native trading brain (no MT5, no Mac, no Wine)

The same checklist engine from the Mac build (`sentry_mac.py` v3.1), ported to run entirely on
**GitHub Actions**. One workflow run = one full scan cycle, every 10 minutes, 24/7 (crypto has no
weekend gap — MT5 demo servers do).

```
┌─ Actions cron (*/10) ─┐   ┌─ this repo = the database ────────────┐
│ run_cycle.py          │──▶│ state.json        (orders/positions)  │
│  1. fetch klines      │   │ ledger.json       (simulated fills)   │
│  2. reconcile fills   │   │ journal.md        (every decision)    │
│  3. evaluate skills   │   │ trades_log.jsonl  (accuracy → sizing) │
│  4. size + fire       │──▶ venue: Coinbase ledger or Alpaca paper │
│  5. push_memory (API) │   └───────────────────────────────────────┘
└───────────────────────┘
```

- `sentry_core.py` — pure brain: EMA/RSI/ATR/Bollinger/pivots, playbook §12 candle engine,
  skill checklists S1/S2/S4/S18/S11, 5-point scoring, accuracy-based self-sizing ($50–$200).
- `broker_ledger.py` — default venue: Coinbase *public* candles + simulated fills in `ledger.json`.
  Zero accounts, zero secrets, nothing to rot.
- `broker.py` — optional Alpaca paper REST client (stdlib only, no pip installs).
- `run_cycle.py` — orchestrator + state machine + **loud-death guards** (exits red on stale or
  thin data, never "scan ok" on nothing) + `push_memory()` (writes memory through the Contents
  API with retry, so two runners can never conflict the way `git push` did).

## Execution modes (one config line)
- **`"execution": "ledger"` (default):** real Coinbase prices, paper fills in `ledger.json`.
  Works with nothing but a repo. `config.json` ships in this mode.
- **`"execution": "alpaca"`:** real paper-trading venue (resting orders on their engine). Needs
  `ALPACA_KEY_ID` + `ALPACA_SECRET` in Actions Secrets. Same brain, different venue.

## Files you care about
- **`journal.md`** — every cycle and every decision, newest at the bottom. This is the bot's diary;
  read it instead of logs (Actions keeps 90 days, git keeps forever).
- **`trades_log.jsonl`** — one row per closed trade (symbol, skill, P/L, bars held, grade). Its
  rolling win rate is what the bot sizes itself with.
- **`state.json`** — machine state: open orders, positions, `sizing` tiers, `seen` (one fire per
  symbol-skill-day), `realized`.
- **`ledger.json`** — cash, positions and marks in ledger mode.
- **`.github/workflows/scan.yml`** — the cron + `permissions: contents: write` that lets it commit memory.

## Run it yourself (3 commands, from a machine with python3)
```bash
git clone https://github.com/akramsakib/sentry.git && cd sentry
python3 run_cycle.py        # one full cycle, no accounts, no keys — prints the decisions
```
To run it as a service on GitHub: push these files to a repo, then
Actions → *sentry-cycle* → **Run workflow**. Green check + a `scan ok · 10 symbols · …`
line landing in `journal.md` = working. A **red** run is the alarm; GitHub emails you.

To make the repo **private** (recommended once you add real keys): GitHub → fine-grained PAT with
`Contents: Read & write` scoped to this repo, then `git remote set-url origin
https://<TOKEN>@github.com/<you>/<repo>.git && git push`. Free-tier private repos get 2,000
Actions minutes/month; this bot burns ~1–2 min per cycle (~5,000/yr at 10-min cadence), so a
private repo at 10-min cadence needs either a paid plan or a slower `cron` (e.g. `*/30`).

## Honest limitations (read before calling it "the same thing")
- **Long-only execution.** Spot crypto can't be shorted here, so short signals are *paper-graded*
  into the accuracy loop (they earn sizing trust, never fire). A futures/perp venue would be needed
  for real shorts.
- **Ledger fills are simulated** against Coinbase quotes; slippage/liquidity on thin alts is
  optimistic. Alpaca mode puts the orders on a real venue, which is the honest next step.
- **Stop/TP enforcement is per-cycle** (up to ~10 min reaction latency, cron jitter included).
  Fine for an M15 playbook; not scalping.
- **Cron is best-effort** — Actions schedules can lag or skip under load; a missed run just delays
  the next reconcile, but know it. Brand-new schedules can also take hours to start.
- **Outcome grading uses the last tracked price vs tp/sl** (a heuristic), not an exchange fill
  report — win/loss flags can be ±1 grade off on violent bars.
- FX & US equities stay on the Mac/MT5 build. OANDA's practice API is the natural adapter if forex
  should move here too — it's one `broker_oanda.py` away.

## Why this design survives what the Mac version suffered
| Failure mode | Mac build | v4 here |
|---|---|---|
| bridge/terminal down | cycles silently with empty quotes | job exits **red** → GitHub notification |
| stale candle window (hardcoded dates) | would trade blind | staleness guard: >3 h-old bar = ALERT |
| JSON quoted through bash | `-32700` spam, 177× | stdlib REST client, no shell at all |
| broker renames a symbol | hardcoded dict breaks | live `/asset-trading-platform/PAPER/reference/crypto` lookup |
| two writers collide | (hit us: `git push` conflict killed a run) | memory via Contents API, re-read + retry on 409 |
| state lost | Mac-local file | state lives in git history, diffable forever |
<!-- push-trigger probe 09:11Z -->
