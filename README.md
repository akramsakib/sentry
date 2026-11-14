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
python3 test_data.py         # offline checks (row order, guards) — must print "0 checks failed"
python3 run_cycle.py         # one full cycle, no accounts, no keys — prints the decisions
```
To run it as a service on GitHub: push these files to a repo, then
Actions → *sentry-cycle* → **Run workflow**. Green check + a `scan ok · 10 symbols · …`
line landing in `journal.md` = working. A **red** run is the alarm; GitHub emails you.

To make the repo **private** (recommended once you add real keys): GitHub → fine-grained PAT with
`Contents: Read & write` scoped to this repo, then `git remote set-url origin
https://<TOKEN>@github.com/<you>/<repo>.git && git push`. Free-tier private repos get 2,000
Actions minutes/month; this bot burns ~1–2 min per cycle (~5,000/yr at 10-min cadence), so a
private repo at 10-min cadence needs either a paid plan or a slower `cron` (e.g. `*/30`).

## Data integrity: the Coinbase candle bug (2026-11-14), kept here so it cannot come back quietly
Coinbase's `/candles` rows are `[time, low, high, open, close, volume]`. An earlier version of
`broker_ledger.py` read them as OHLC, which made every bar "bullish" (close=high > open=low) and
turned `high-low` into the *body*. Result: `C-*-three-soldiers` fired on five symbols at once with
stops 0.04% wide, and `risk / stop-distance` then asked for 3 454 SOL — $261k notional to risk $100.
`test_data.py` pins the row order, the forming-candle pop, an impossible-bar rejection, and both
sizing guards; the workflow runs it before every cycle, so a regression is a red run, not a bad trade.

## Cadence: GitHub's cron is throttled on this account (read this)
Measured on 2026-11-14: `sentry-cycle` declares `*/10 * * * *` and every *other* trigger
(`push`, `workflow_dispatch`, `repository_dispatch`) fires in seconds, but **zero** scheduled
runs appeared for ~4 h. It is not this repo: a sibling repo of the same account
(`Trading-Bot`, cron `3,18,33,48 * * * *` = 96 runs/day) delivered **4** runs in the last 24 h
with 4–8 h gaps, and its 1 358 historical schedule runs prove the mechanism works there.
GitHub is queue-throttling (or silently muting) high-frequency crons for this account — a
community-reported behaviour (GitHub community discussions #208110, #209473, #209838, Sep–Nov 2026).

Three ways to get a real clock, best first:

1. **External pinger → `repository_dispatch` (recommended, free).** Any 10-min cron that POSTs:
   ```bash
   curl -sS -X POST \
     -H "Authorization: Bearer $GH_PAT" -H "Accept: application/vnd.github+json" \
     https://api.github.com/repos/OWNER/REPO/dispatches \
     -d '{"event_type":"sentry-tick"}'
   ```
   `GH_PAT` = a fine-grained token scoped to this repo with **Actions: Read and write** only.
   A Cloudflare Worker + Cron Trigger is 15 lines and free; a plain `crontab` on any always-on
   box (including the Mac) works too. Verified from a cold shell on 2026-11-14: `204` → run
   created in ~3 s, full cycle, memory committed (that is how run #8 happened).
2. **Let the watchdog push it along.** `sentry-watchdog` (hourly) exits red when the journal is
   stale **and dispatches a fresh cycle itself** — `workflow_dispatch` is one of the two events a
   `GITHUB_TOKEN` may fire, so no PAT is needed for that path. You get at least a few cycles/day
   even if GitHub never honours the 10-min cron.
3. **Accept it.** Crypto has no session gap, so a cycle every 4–8 h is still a usable swing bot;
   the state machine reconciles whatever happened while it slept. Do not call it an M15 bot then.

Do **not** "fix" this by ending each run with a delayed self-dispatch: the sleep needed to space
runs would keep a runner occupied 24/7, which is exactly what GitHub's abuse detection disables.

## Honest limitations (read before calling it "the same thing")
- **Long-only execution.** Spot crypto can't be shorted here, so short signals are *paper-graded*
  into the accuracy loop (they earn sizing trust, never fire). A futures/perp venue would be needed
  for real shorts.
- **Ledger fills are simulated** against Coinbase quotes; slippage/liquidity on thin alts is
  optimistic. Alpaca mode puts the orders on a real venue, which is the honest next step.
- **Stop/TP enforcement is per-cycle** (up to ~10 min reaction latency, cron jitter included).
  Fine for an M15 playbook; not scalping.
- **Cron is best-effort** — on this account it is actively throttled; see *Cadence* above before
  trusting the 10-min interval. A missed run only delays the next reconcile (stateless per cycle).
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
