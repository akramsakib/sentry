# v4.7.9 — what shipped, and the one step still on you

Shipped 2026-11-18 as `41c94a71` + `8d722ef9` on `akramsakib/sentry:main` (CI `sentry-cycle` green on both;
26 files verified byte-equal, then the switch kit added as a 27th and the CCTV URL helper as a 28th).
`tools/mac/sentry_mac.py` and `tools/mac/account_switch.sh` are now IN the release — before this the resident
every figure came from was not. All Mac files verified **byte-identical** between the repo and `~/hermes_sentry/`:

Two repairs landed on the resident after that first row was written, both found while answering "sentry down?",
both mine, both now pinned by a test:

1. **`chart_thin = {}` was deleted by my own splice** (`_pmargin2.py` used a replace where an insert belonged).
   `publish_watch` then raised `NameError` every cycle for ~17 hours — the per-cycle `try/except` swallowed it,
   so the desk looked healthy and only the forex watch was dead. Now `test_data.py` §34 checks the line order
   (init < use < publish call) rather than trusting a grep.
2. **`retcode 10015 Invalid price` was not the broker being flaky — and it was not one thing.**
   91 `CHECK/SEND FAILED` lines, **79 of them XAUUSD against 26 gold fills ever**.  The file also holds 148
   bare `"jsonrpc...` reply dumps, all dated 11-13, from an `UNPARSED send result` line this build no
   longer has — which is worth saying because counting the string `10015` overstates the failures: 211
   mentions, 91 refusals.  Get the number from the tag, not the code. Two causes were tangled in that number:
   - `send_order` substituted the raw Python float into the JSON (`1.3165645839210065` for a 5-digit
     symbol; `154.13837845882833` for a 2-digit one) while the journal printed the same order through
     `rnd()` — so **the log and the order disagreed**, and no amount of reading the journal could have
     found the real cause. Fixed by `fmt_px` at the one place the payload is filled in and at the two
     chandelier-trail sites, which hardcoded 5 digits and so were wrong for gold and the equity symbols.
   - the refusals themselves are **geometry**: a short candidate drawn from a closed candle, retried
     every cycle after the market crossed its level. Probed live, three calls differing only in
     type/price — `sell stop @1.31256` ok, `sell limit @1.31656` ok, `sell stop @1.31656` refused
     10015 (GBPUSD was at 1.3154/1.3156). Fixed by `pending_geom`, which refuses with a reason *before*
     spending the call, counts the hold into `state.geom_held`, and does **not** burn the day's fire key
     — a pullback makes the level valid again. Nothing re-prices and nothing converts stop to limit: a
     fade of the rally is not the trade the signal asked for.
   `fmt_px(sym, v)` (the digits half) is applied at the one place the payload is filled in, and at the two
   chandelier-trail sites that hardcoded 5 digits; volumes never pass through it — formatting, not sizing.
3. **The alert queue was full and had never drained** — asked "alerts queued?", measured at 23:56 KL:
   `alerts.outbox` 200 lines = exactly the cap (oldest 11:08, newest 23:50), `alerts.sent.log` **2 lines,
   both a bridge-drain test from 11-17 02:45**, no `gmail_smtp.json`, and `HERMES_ALERT_WEBHOOK` absent from
   `com.hermes.radar`'s environment (`launchctl print` showed only `PATH` and `XPC_SERVICE_NAME`). So every
   line failed the "did anything off the Mac get this" test and was re-queued, which meant three things: the
   desk re-notified all 200 lines **every 60 seconds**, the trim discarded the **oldest** lines regardless of
   what they were (116 advisories held against 4 fills — the FILLs were what got thrown), and the loss was
   counted nowhere. Fixed locally, no new secret: `trim_outbox` keeps urgent lines first and drops the noise,
   `alerts.notified` is a sha1 watermark so a line is announced once instead of forever, and `alerts.dropped`
   counts what overflowed — all three published in `channels` (`queued/cap`, `urgent_held`, `dropped`,
   `full`) and printed on the page. Re-measured at 00:02: 200 held, **70 urgent** (an 11:08 refusal survives,
   which it would not have before), `dropped 2`, notifications 183→185 rather than +200.
   `test_data.py` §38 runs the shipped `trim_outbox`/`flush_outbox` against stubbed channels — including the
   check that a line with no channel **stays queued** rather than being dropped to look tidy.
   **Then, asked "why 200?":** because it was never a queue-depth requirement — the shipped line was a bare
   `remaining[-200:]` with no name and no comment, and 200 is this build's house number for "recent history"
   (the resident trims its fired-key list with `del done[:-200]`).  It exists only so an append-only spool
   cannot grow forever: nothing truncates `alerts.outbox` except this rewrite, and the page displays
   `tail(OUTBOX_F, 10)` regardless of the cap.  As a retention window it was actively costing things: 200
   lines = 29,832 bytes and 13 hours, so anything older than half a day was being discarded while no channel
   existed.  Retention is free — `OUTBOX_CAP = 5000` ≈ 750 KB — so the number is now a named constant at the
   top of the file, passed at flush time rather than bound at import, with the notify watermark tracking it.
   Measured after the kickstart: `cap 5000`, `queued 200`, `full false`, `urgent_held 81`, `dropped 12`
   (frozen, cumulative — nothing further is discarded until 5,000 lines build up).
   Suite: **585 PASS / 0 failed** (sections 34–38 are new since the first row of this file was written).
4. **The live-account interlock, added before he logs a VT Markets live account into the terminal.**  Up to
   tonight the only thing between the loop and a real balance was `"entries_enabled": true` in
   `desk_mode.json` — one boolean written for rehearsal — and the terminal's own AutoTrading switch does not
   gate this path (it gates EAs; these sends go through the terminal's MCP trade API).  Now `send_order`
   refuses anything while `account_is_real()` and `desk_mode.json` lacks `"live_confirmed": true`, journalling
   both steps by name; `note_account_kind()` mirrors the type from the one place that reads the terminal, and
   **"type unknown" is treated as real, not as safe** (costs a cycle at startup; the reverse costs money).
   A real account also stops inheriting the demo's ceiling: with no `risk_max_frac_of_equity` chosen, the
   per-trade cap is 1 % of equity instead of 10 % — measured on the live deployment the demo still reads
   `max_frac 0.1`, `type 'demo'`, zero live-guard refusals, so the rehearsal is untouched.
   `test_data.py` §39 (17 checks).  Then, when he said he wants the live account traded as it trades today,
   `desk_mode.json` was pinned to `{ entries_enabled: true, live_confirmed: true, risk_max_frac_of_equity: 0.1 }`
   — the 0.10 is the demo's own number written down, not inherited, so nothing about the sizing changes when
   the login changes.  Proven against the deployed file with the terminal stubbed: account type `real` now
   reaches the terminal and returns a ticket; `sizing.max_frac` on the live demo still reads 0.1.
   **Two bugs found in the switch kit while doing it** (§40, 7 checks, running the shipped script in a throwaway
   HOME): `fresh` wrote a two-key `desk_mode.json`, silently dropping `live_confirmed` and the risk ceiling;
   and because it left no stamped backup of its own, `resume` after `fresh` restored a *paused* file — press
   resume, stay paused, no explanation.  `fresh` now carries every desk choice across, writes the stamped
   backup with `entries_enabled: true` while opening the live file paused, and the original is still archived
   verbatim.  Suite: **609 PASS / 0 failed**.

5. **The dashboard now carries the ledger: total trades, wins, losses and the profit or loss.**  He asked for
   it after the performance read-out, and every figure was already published by something — `live_record` in
   `state.json` for the terminal leg, each crypto book's `grades` + `realized` — so `money_block()` reads
   those fields instead of re-deriving anything, and the page prints an em dash wherever nobody published a
   number (a 0 there would read as "it broke even", which is a different claim).  Three decisions worth
   keeping:  **trades means SUBMITTED** (`live_record.sent`, 135) with the graded count beside it and "no
   close yet" (74) named as such, because submitted / filled / graded is the distinction the desk is built
   on;  **shadow dollars are shown but never pooled as the account's** — a book counts as real only if it
   publishes `state: live` and no `blocked_on`, so a field nobody wrote fails closed on the money claim
   (`real_usd` 1,659.23 against `shadow_usd` -2,889.23, printed as separate figures in the footer row);
   and  **no win rate and no pooled net R live here** — `grade_stats` is the one definition of the ratios,
   and a second net-R headline (+4.07R over sent trades) beside the graded record's (+0.97R over every
   graded row) differs only by its denominator, which is how a dashboard gets distrusted.  The account kind
   printed next to the dollars is the terminal's own word for itself (`demo`), so a demo profit cannot be
   read on a phone as real money.  `today` discloses `usd_n`: a graded row with no dollar figure still counts
   as a result, so the note says "only 2 of 3 rows carry a $ figure" instead of summing quietly.
   Suite: **638 PASS / 0 failed** (§41, 29 checks); `fx_watch_test.py` 0 failed; `node --check` parses the
   14,638 chars of page JS.  Measured on the deployed page after the kickstart: totals `trades 192 | W 54
   L 60 void 4 | $ -1230.00 (real 1659.23 / shadow -2889.23)`, MT5 leg `135 · 40W/21L · $1659.23 · demo`,
   the graded record's own line unchanged at 47.9 %, desk still `watch_error None` on the demo.

| file | md5 | bytes |
|---|---|---|
| `sentry_mac.py` (the resident — now in the repo too) | `4b907b9e6ad9c4eb1d6542cc4d539be5` | 111,638 |
| `monitor.py` (desk page) | `e7389c2aa6c84e78f96792b4f9d5d640` | 52,999 |
| `account_switch.sh` (switch kit) | `f1d01f716af6a4d08b8b510d71b2e35d` | 17,827 |
| `trade_radar.py` (radar page) | `1b482e08e485103ed2f56f5c6b15781e` | 87,361 |

## The two things it could not do before

1. **It could not see the account it trades.** Sizing came from a fixed $50–$200 risk band with no knowledge of
   equity, and a size under the broker's 0.01 minimum returned `0` — an order too small for the account simply
   vanished, with nothing journalled. `size_report()` now reads the account every cycle and returns a verdict:
   `ok` / `round_up_to_min_lot` / `min_lot_too_big` / `over_max_lot` / `no_stop`. The 10%-of-equity ceiling
   clamps the *requested* risk, not just the broker's floor. `desk_mode.json` key
   `"risk_max_frac_of_equity"` (0 = guard off).

2. **It could not tell whether its own trades won.** `mcp_call()` ended in `head -c 300`, so the position-history
   reply was always truncated and `except Exception: pass` hid it. Result: **94 sent rows, 0 grades**, while the
   paper track (which grades *rejected* candidates at ±1R) was what the desk quoted as a win rate. Grading now
   joins on the order comment `Sentry <skill>` (at the terminal's 31-char limit), or on the venue ticket when we
   have one; 6-hour window for a comment match, 10 days for a ticket; one close settles one row; rows with no
   close stay **ungraded on purpose**.

## Measured on your live account (login 5058788329, MetaQuotes-Demo, 101,155.96 USD, *demo*)

* `capped_today: 0`, `refused_today: {}`, EURUSD still 0.17 lots / $76.50 → **the guard changed nothing here**, which was the requirement.
* `0` lines matching `REFUSED` in the whole 2,900-line journal.
* Live record now on both pages: **94 sent, 61 graded from the terminal's own closes, 40W/21L, +14.52R, +$1,659.23 USD, 33 ungraded.** The paper track is quoted beside it as its own number (-12.48R) — the two are not the same measurement and must never be summed.
* `bash account_switch.sh status` prints the same live record, the sizing verdicts, and 63 `OUTCOME` journal lines exist where there were 0 grades. Desk pill says `demo account … (reported by the terminal this cycle)`. It used to be inferred by grepping the
  resident's *header comment* for the words "demo account" — which is how the card could print a confident claim
  that nothing on the desk had actually measured. That is fixed, and the fallback is now labelled as an inference.

## Still yours to do: the $50 demo

No API can open an account (no MCP tool, no URL scheme, `accounts.dat` is encrypted), so this is a click:

1. On the Mac, MetaTrader 5 → **File → Open an Account → MetaQuotes → MetaQuotes-Demo → Create a demo account**
   * email `akramhossainsakib@gmail.com`, phone `+60183560937`, currency **USD**, deposit **50**
     (if the form refuses 50, take 100 — per-trade risk then halves to ~3.5% instead of ~7%)
   * hedging, 1:100
2. Copy the **master password** out of the confirmation dialog, then:
   ```
   bash ~/mac_connect.sh 'cd ~/hermes_sentry && bash account_switch.sh fresh <LOGIN> <PASSWORD> "MetaQuotes-Demo"'
   bash ~/mac_connect.sh 'cd ~/hermes_sentry && bash account_switch.sh verify'   # want: balance == 50.00
   ```
3. Phone MT5 → *My existing account* → server `MetaQuotes-Demo` → login + **investor** password
   (`account_switch.sh handoff` prints them for you to copy; nothing is persisted on the desk).

**Margin, measured from your broker (not assumed):** `trade_order_calc_margin` answered AMD $510.63, XAUUSD $38.47, NVDA $158.71, GBPUSD $13.21, EURUSD $11.00 for ONE minimum unit. Margin follows price, not the account, so an early hand-computed $220 for AMD was wrong by more than double — which is why the resident measures it instead of deriving it from an assumed leverage (`account_info` publishes none).

**What to expect on $50, from the shipped code and your broker's own numbers:** the floor is the problem, not the strategy.
`0.01` lot of XAUUSD already risks the whole width of a normal stop (~$33 on the sizes this build uses) = 67% of
$50 → **gold is refused**. EURUSD/GBPUSD become placeable at 0.01 lot with risk capped to ~$5. The replay of
your 79 real fills said the same thing: as-coded **$50.00, 0 of 79 trades placeable**; forced to the broker
minimum **$22.65 (−54.7%)**; 5%-of-equity risk **$60.83**. A coherent base for this build's own $50–$200 band is
**$5k–$10k** — that number is arithmetic on your fills, not advice.
