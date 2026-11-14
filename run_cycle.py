"""Sentry v4.3 (GitHub-native) — one full scan/manage cycle per run.

Designed to be invoked by .github/workflows/scan.yml every 10 minutes.
State of record = files in this repo (state.json, journal.md, trades_log.jsonl),
committed back by the workflow. The job exit code is the alarm: data or broker
failure -> non-zero -> red ✗ in Actions + GitHub notification. Silent staleness
is not an option (lesson from the Mac build).

Env: ALPACA_KEY_ID, ALPACA_SECRET (paper keys). Fixtures for CI-less testing:
SENTRY_FIXTURES=<dir> reads bars from <dir>/<SYMBOL>.json and skips all writes.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import sentry_core as core

CFG = json.load(open(os.path.join(HERE, "config.json")))
_CID_TS = re.compile(r"(\d{13})n\d+$")   # sentry{SYM}{ms}n{seq} -> the ms doubles as the placement clock
EXEC_MODE = CFG.get("execution", "ledger")
# Venue selection is one config line ("execution"). coinbase = real orders via
# broker_coinbase.py; it falls back to the shadow ledger ONLY when no key exists in this runner,
# and says so in the journal + summary so "did it place a real order?" is never a guess.
CB_KEYED = EXEC_MODE == "coinbase" and bool(os.environ.get("COINBASE_API_KEY"))
LIVE = False
VENUE = "shadow-ledger"
if EXEC_MODE == "alpaca":
    import broker                                            # Alpaca (paper host by default)
    LIVE = True
    VENUE = "alpaca"
elif CB_KEYED:
    import broker_coinbase as broker                         # real Coinbase Exchange orders
    LIVE = True
    VENUE = "coinbase-live(DRY)" if os.environ.get("COINBASE_DRY") == "1" else "coinbase-live"
elif EXEC_MODE == "coinbase":
    import broker_ledger as broker                           # venue chosen, key not in place yet
    VENUE = "shadow-ledger(coinbase-no-key)"
else:
    import broker_ledger as broker
STATE_F = os.path.join(HERE, "state.json")
JOURNAL_F = os.path.join(HERE, "journal.md")
TL_F = os.path.join(HERE, "trades_log.jsonl")
FIXDIR = os.environ.get("SENTRY_FIXTURES")
DRY = bool(FIXDIR) or os.environ.get("SENTRY_DRY") == "1"
# "LIVE" means one thing only: this venue moves real money. Alpaca's paper host and the Coinbase
# sandbox stay False, so the live gates never starve a paper venue that still needs fills to grade.
_host = (getattr(broker, "TRADE", "") or getattr(broker, "BASE", "")).lower()
LIVE = LIVE and not DRY and "paper-api" not in _host and "sandbox" not in _host


def now():
    return datetime.now(timezone.utc)


JOURNAL_LINES = []
TL_LINES = []


def journal(line):
    stamp = now().strftime("%m-%d %H:%M UTC")
    with open(JOURNAL_F, "a") as f:
        f.write(f"- **{stamp}** {line}\n")
    JOURNAL_LINES.append(f"- **{stamp}** {line}")
    print(f"[{stamp}] {line}", flush=True)


def fail(msg):
    """Loud death: journal + non-zero exit -> red workflow run -> notification."""
    journal(f"ALERT — {msg}")
    print(f"FATAL: {msg}", file=sys.stderr)
    sys.exit(1)


def load_state():
    try:
        s = json.load(open(STATE_F))
    except Exception:
        s = {}
    day = now().strftime("%Y-%m-%d")
    if s.get("day") != day:
        s.update({"day": day, "fired_today": []})
    s.setdefault("fired_today", [])
    s.setdefault("open_cids", {})
    s.setdefault("pos_state", {})
    return s


def save_state(s):
    with open(STATE_F, "w") as f:
        json.dump(s, f, indent=1)


def tl_log(rec):
    rec["ts"] = now().strftime("%Y-%m-%d %H:%M")
    with open(TL_F, "a") as f:
        f.write(json.dumps(rec) + "\n")
    TL_LINES.append(json.dumps(rec))


def tl_rows():
    try:
        return [json.loads(x) for x in open(TL_F) if x.strip()]
    except FileNotFoundError:
        return []


def fetch_bars(sym):
    """Returns {'1h': [...], '15m': [...], '1d': [...]} or raises via fail()."""
    if FIXDIR:
        fn = os.path.join(FIXDIR, sym.replace("/", "") + ".json")
        d = json.load(open(fn))
        for tf, need in (("1h", 60), ("15m", 20), ("1d", 12)):
            if len(d.get(tf) or []) < need:
                fail(f"fixtures thin for {sym}: {tf} has {len(d.get(tf) or [])}, need {need}")
        return d, d.get("_asof", 0)
    try:
        h1 = broker.crypto_bars(sym, "1Hour", 200)
        m15 = broker.crypto_bars(sym, "15Minute", 200)
        d1 = broker.crypto_bars(sym, "1Day", 60)
    except broker.BrokerError as e:
        fail(f"data fetch error {sym}: {e}")
    # staleness guard: last closed 1h bar must be younger than 3h (crypto is 24/7)
    if h1:
        ts = datetime.fromisoformat(h1[-1]["t"].replace("Z", "+00:00")).timestamp()
        if now().timestamp() - ts > 3 * 3600:
            fail(f"STALE DATA: {sym} last closed 1h bar is >3h old — exchange or feed is down, not a 'no signal'")
    if len(h1) < 60 or len(m15) < 20 or len(d1) < 12:
        fail(f"THIN DATA: {sym} h1={len(h1)} m15={len(m15)} d1={len(d1)} — expected a healthy history")
    return {"1h": h1, "15m": m15, "1d": d1}, 0


def live_risk_cap(risk, equity, cfg):
    """(risk_after_caps, notes). Live risk is the smallest of: what the accuracy sizer asked for,
    the flat ceiling, and `live_max_risk_frac` of the account. Never the other way round — the stop
    distance belongs to the checklist, and trimming size to fit an account is how a $100 trade
    becomes a $1.37 trade that only pays fees."""
    frac = float(cfg.get("live_max_risk_frac", 0.01))
    caps = [("config.live_max_risk", float(cfg.get("live_max_risk") or 0)),
            (f"{100 * frac:g}% of equity", round(equity * frac, 2))]
    out, notes = float(risk), []
    for label, cap in caps:
        if cap and out > cap:
            notes.append(f"${out:.2f} -> ${cap:.2f} ({label})")
            out = cap
    return round(out, 2), notes


def entry_sane(otype, entry, mkt, tol=0.0005):
    """Is this resting order actually an entry, or is it a market order in disguise?

    A BUY LIMIT above the tape and a BUY STOP below it both execute the instant they are placed:
    the "pullback at 65 964" I would have sent with BTC at 65 454 (2026-11-14, shadow fill) would
    have bought immediately, 0.8 % worse than market, paid a taker fee, and been logged as a
    signal. The level has to be on the far side of the price for it to mean anything.
    """
    if not mkt or not entry:
        return False, "no reference price"
    stop_side = str(otype).endswith("_stop")
    buying = not str(otype).startswith("sell")
    if stop_side:
        ok = entry > mkt * (1 - tol) if buying else entry < mkt * (1 + tol)
        why = "stop must sit beyond the tape (breakout trigger), not under it"
    else:
        ok = entry < mkt * (1 + tol) if buying else entry > mkt * (1 - tol)
        why = "limit must rest on the far side of the tape (pullback), or it fills instantly"
    return (True, "") if ok else (False, why)


def reanchor(entry, sl, tp, mkt, otype, tol=0.0005):
    """Return (entry_price_to_use, note, ok).

    Several skills are judged on the LAST CLOSED bar (Donchian: "closed above the n-bar high";
    band fade: "price at or through the band"). By the time the cycle runs, that trigger level is
    already behind the tape, so the order built on it is not a resting entry: a buy limit above the
    tape or a buy stop below it executes the instant it is accepted, at the market, not at the
    level. Silently sending that would (a) pay a taker fill nobody intended, (b) book R from a
    price that was never available. So: honour the signal by entering at the tape, and recompute R
    from the price actually paid. If the target is now inside the entry, the trade is already over.
    """
    if not mkt or not entry:
        return entry, "no reference price", False
    sane, why = entry_sane(otype, entry, mkt, tol)
    if sane:
        return entry, "", True                                 # resting where it should rest
    is_sell = str(otype).startswith("sell")
    if (not is_sell and mkt >= tp) or (is_sell and mkt <= tp):
        return entry, "target already inside the tape before entry", False
    return mkt, (f"trigger {entry:.10g} is already through the tape {mkt:.10g} — entering at market, "
                 f"R recomputed ({why})"), True


def live_gate(rows, s):
    """What must be true before real money moves. Returns (allow_new_entries, why_not).

    Deliberately narrow: exits, protective stops and TTL expiry always run, because a resting
    position has to be managed whether or not the gates are happy. Only NEW entries are blocked.
    The reasons are all lessons from this account, not paranoia:
      * live_ack  — a leaked secret must not be enough to start trading.
      * clock     — GitHub's scheduler delivers a few cycles a day here, not one per 10 min, so
                    an entry can sit unmanaged for hours; only a fresh heartbeat justifies that.
      * accuracy  — the sizer scales off graded outcomes; live trading with zero of them would
                    put a blind number on a real account.
    """
    if not LIVE:
        return True, ""
    if CFG.get("live_ack") is not True:
        return False, ("config.live_ack is not true — set it in config.json once you have read the "
                       "risk (real orders, real money, no undo)")
    graded = [r for r in rows if r.get("fired") and r.get("result")]
    need = int(CFG.get("min_grade_before_live", 8))
    if len(graded) < need:
        return False, f"only {len(graded)} graded outcomes, {need} required before live sizing"
    gap_h = float(CFG.get("max_gap_h", 2.0))
    last = float(s.get("last_cycle") or 0)
    if not last:
        return False, f"no heartbeat yet — need one clean cycle within {gap_h:g} h before live entries"
    age_h = (time.time() - last) / 3600.0
    if age_h > gap_h:
        return False, f"last cycle was {age_h:.1f} h ago (> {gap_h:g} h) — the book would sit unmanaged"
    return True, ""


def live_positions():
    if DRY:
        return []
    try:
        return broker.positions()
    except broker.BrokerError as e:
        fail(f"positions read failed: {e}")


def run():
    t0 = time.time()
    sizer = core.Sizer(CFG["base_risk"], CFG["min_risk"], CFG["max_risk"])
    s = load_state()
    rows = tl_rows()
    syms = CFG["symbols"]
    tf_map = {}
    for sym in syms:
        tf_map[sym], _ = fetch_bars(sym)
        journal_ok = True
    live = {p["symbol"]: p for p in live_positions()}
    acct = None if DRY else broker.account()

    # a0) expire resting entries whose setup has gone stale. Matters because GitHub's cron on
    # this account delivers a few cycles per day, not one per 10 min: an H1 breakout trigger from
    # 13:00 is not the same trade at 03:00, it is just an old order that happens to be reachable.
    ttl_h = float(CFG.get("pending_ttl_h", 6.0))
    for cid in list(s["open_cids"].keys()):
        m = _CID_TS.search(cid)
        if not m:
            continue
        age_h = (time.time() - int(m.group(1)) / 1000.0) / 3600.0
        if age_h <= ttl_h:
            continue
        meta = s["open_cids"].pop(cid)
        if not DRY:
            try:
                for o in broker.open_orders():
                    if (o.get("client_order_id") or "") == cid:
                        broker.cancel_order(o["id"])
            except broker.BrokerError as e:
                journal(f"NOTE — could not cancel expired pending {cid}: {e}")
        journal(f"EXPIRED — {meta['sym']} {meta['skill']}: entry trigger rested {age_h:.1f} h "
                f"(>{ttl_h:g} h), setup no longer valid")
    # ---------- 1) reconcile: fills, exits, protective orders ----------
    # a) positions that vanished since last cycle -> grade the outcome
    for sym, ps in list(s["pos_state"].items()):
        if sym not in live:
            last = ps.get("last_price") or ps["entry"]
            win = (last > ps["tp"]) if ps["side"] == "long" else (last < ps["tp"])
            res = "win" if win else "loss"
            r_mult = round((last - ps["entry"]) / ps["r_dist"], 2) if ps.get("r_dist") else 0
            tl_update(sym, res, last, r_mult)
            journal(f"CLOSED {sym} — graded {res} ({r_mult:+.2f}R) | stop/target orders cleaned by exchange/reconcile")
            if not DRY:
                try:
                    broker.cancel_all()  # cancel any resting tp/stop remnants; pendings re-placed if fresh
                except broker.BrokerError:
                    pass
            del s["pos_state"][sym]
    # b) current positions -> enforce SL/TP + breakeven + ATR trail
    for sym, p in live.items():
        cur = float(p.get("current_price") or 0)
        qty = float(p.get("qty") or 0)
        side = "long" if qty > 0 else "short"
        ps = s["pos_state"].get(sym)
        if not ps:
            continue  # not ours (manual) — leave alone
        if not cur:
            continue
        ps["last_price"] = cur
        entry, sl, tp, rd = ps["entry"], ps["sl"], ps["tp"], ps["r_dist"]
        fav = (cur - entry) if side == "long" else (entry - cur)
        if ps.get("be") is None and fav >= rd:
            ps["be"] = entry
            journal(f"BE +1R: {sym} stop -> entry {entry}")
        new_sl = ps.get("be") or sl
        if side == "long" and cur - 2 * (atr1h(sym, tf_map)) > 0 and fav >= 1.5 * rd:
            cand = round(cur - 2 * atr1h(sym, tf_map), 8)
            if cand > new_sl:
                new_sl = cand
        if (side == "long" and cur <= new_sl) or (side == "short" and cur >= new_sl):
            journal(f"EXIT {sym}: price crossed stop {new_sl} (cur {cur}) — market close")
            if not DRY:
                broker.place_order("sell" if side == "long" else "buy", sym, qty=abs(qty), otype="market")
        elif not DRY and new_sl != ps.get("sent_sl"):
            # (re)arm a server-side protective stop at the live sl
            broker.place_order("sell" if side == "long" else "buy", sym, qty=abs(qty),
                               otype="stop", stop_price=new_sl, tif="gtc", cid=f"sentryprot{int(time.time())}")
            ps["sent_sl"] = new_sl
    # c) filled pendings -> adopt as positions; stale pendings -> cancel
    if not DRY:
        try:
            opens = broker.open_orders()
        except broker.BrokerError as e:
            fail(f"open orders read failed: {e}")
        open_by_cid = {o.get("client_order_id"): o for o in opens}
        for cid, meta in list(s["open_cids"].items()):
            if cid not in open_by_cid:
                o = broker.order_by_cid(cid)
                if o and o.get("status") == "filled":
                    sym = meta["sym"]
                    s["pos_state"][sym] = {"side": "long", "entry": float(o["filled_avg_price"] or meta["entry"]),
                                           "sl": meta["sl"], "tp": meta["tp"], "r_dist": meta["r_dist"],
                                           "qty": float(o.get("filled_qty") or meta["qty"]), "skill": meta["skill"],
                                           "be": None, "sent_sl": None, "last_price": None}
                    journal(f"FILL — {sym} {meta['skill']} {o.get('filled_qty')}@{o['filled_avg_price']} sl{meta['sl']} tp{meta['tp']}")
                s["open_cids"].pop(cid, None)
        for o in opens:  # kill strays older than the day (Sentry tags all of its own via cid prefix)
            cid = o.get("client_order_id") or ""
            if cid.startswith("sentry") and cid not in s["open_cids"] and o.get("side") == "buy":
                broker.cancel_order(o["id"])
                journal(f"CANCEL stray sentry pending {cid}")

    # ---------- 2) scan for new candidates ----------
    allow_new, why_not = live_gate(rows, s)
    if LIVE and not allow_new:
        journal(f"GATE — venue {VENUE} armed but NO new entries: {why_not}")
    fired = 0
    equity = float((acct or {}).get("equity") or 100000.0)
    min_frac = float(CFG.get("min_stop_frac", 0.004))
    max_nf = float(CFG.get("max_notional_frac", 0.25))
    for sym in (syms if allow_new else []):
        cands = core.evaluate_symbol(sym, tf_map[sym], CFG["min_score_fire"])
        # one candidate per symbol-skill-day, no pending/position crowding
        pending_syms = {m["sym"] for m in s["open_cids"].values()}
        for c in cands:
            if sym in pending_syms:
                continue  # one pending per symbol, period — zombie-book guard
            fkey = f"FIRE|{sym}|{c['skill']}|{s['day']}"
            if fkey in s["fired_today"]:
                continue
            s["fired_today"].append(fkey)
            del s["fired_today"][:-200]
            is_sell = c["otype"].startswith("sell")
            risk = sizer.size(c["skill"], c["score"], rows)
            rid = f"{sym}|{c['skill']}|{c['entry']}"
            if is_sell and sym not in s["pos_state"]:
                tl_log({"rid": rid, "sym": sym, "skill": c["skill"], "otype": c["otype"], "entry": c["entry"],
                        "sl": c["sl"], "tp": c["tp"], "score": c["score"], "risk": risk, "fired": False,
                        "note": "paper: no crypto shorting on spot"})
                journal(f"CANDIDATE(score {c['score']}/5) — {sym} {c['skill']} {c['otype']} {c['entry']} sl{c['sl']} tp{c['tp']} — paper-graded (spot can't short)")
                continue
            if sym in pending_syms or sym in s["pos_state"]:
                tl_log({"rid": rid, "sym": sym, "skill": c["skill"], "otype": c["otype"], "entry": c["entry"],
                        "sl": c["sl"], "tp": c["tp"], "score": c["score"], "risk": risk, "fired": False})
                journal(f"SKIP — {sym} {c['skill']}: already have pending/position in play")
                continue
            if len([o for o in s["open_cids"].values()]) + len(s["pos_state"]) >= CFG["max_open"]:
                journal(f"NOTE — {sym} {c['skill']}: soft cap on open items ({CFG['max_open']}) — advisory, skipping")
                continue
            tape = 0.0
            try:
                tape = float(tf_map[sym]["15m"][-1]["c"])
            except (KeyError, IndexError, TypeError, ValueError):
                pass
            entry, note, ok = reanchor(c["entry"], c["sl"], c["tp"], tape, c["otype"])
            if not ok:
                tl_log({"rid": rid, "sym": sym, "skill": c["skill"], "otype": c["otype"], "entry": c["entry"],
                        "sl": c["sl"], "tp": c["tp"], "score": c["score"], "risk": risk, "fired": False})
                journal(f"SKIP — {sym} {c['skill']}: {note}")
                continue
            if note:
                journal(f"RE-ANCHORED — {sym} {c['skill']}: {note}")
            r_dist = abs(entry - c["sl"])
            # A stop a few ticks from entry is not a risk level, it is spread noise: the
            # "risk / distance" formula then prints an absurd size (2026-11-14 run #8 asked
            # for 3 454 SOL — $261k notional to risk $100). Refuse those instead of trading them.
            if r_dist < entry * min_frac:
                journal(f"SKIP — {sym} {c['skill']}: stop only {100 * r_dist / entry:.3f}% of price "
                        f"(<{100 * min_frac:.2f}%) — spread noise, not a risk level")
                continue
            # On a live venue the sizer's number is a REQUEST: a small account must shrink the RISK
            # it takes, never the distance of its stop (shrinking size instead silently trades a
            # different, degenerate bet — the $250-ceiling rehearsal on 2026-11-14 turned a $100
            # risk into $1.37 of "risk", which is pure spread and fees).
            if LIVE:
                risk, clamps = live_risk_cap(risk, equity, CFG)
                for note_ in clamps:
                    journal(f"LIVE RISK CLAMP — {sym} {c['skill']}: {note_}")
            qty = risk / r_dist
            # and never let a "small risk" order grow past a sane slice of the account
            notional = entry * qty
            if LIVE and notional > equity * max_nf:
                journal(f"SKIP — {sym} {c['skill']}: risking ${risk:.2f} through a "
                        f"{100 * r_dist / entry:.2f}% stop needs ${notional:,.0f} notional = "
                        f"{notional / equity:.1f}x equity. Cap is {100 * max_nf:.0f}% (${equity * max_nf:,.0f}) "
                        f"— this trade wants a ~${notional / max_nf:,.0f} account. Fund it or accept fewer "
                        f"signals; the size is NOT being quietly trimmed.")
                continue
            if notional > equity * max_nf:
                qty = equity * max_nf / entry
                risk = qty * r_dist
                journal(f"CAPPED — {sym} {c['skill']}: notional ${notional:,.0f} over {100 * max_nf:.0f}% "
                        f"of equity (${equity * max_nf:,.0f}) → size {qty:.6f}, risk now ${risk:.0f}")
            if entry * qty < CFG["min_notional"]:
                journal(f"SKIP — {sym} {c['skill']}: qty below min notional (risk ${risk} too small for ${entry:.2f} price)")
                continue
            s["cid_seq"] = s.get("cid_seq", 0) + 1
            cid = f"sentry{sym.replace('/', '')}{int(time.time() * 1000)}n{s['cid_seq']}"[:60]
            # breakout entries must ride a real STOP order (a buy-limit above market would
            # fill instantly at market, faking the breakout); pullbacks use GTC LIMIT at level
            stop_entry = c["otype"].endswith("_stop")
            if DRY:
                order_ok = True
                pending_syms.add(sym)
                journal(f"DRY-FIRE — {sym} {c['skill']} {c['otype']} qty {qty:.6f} @ {entry} sl{c['sl']} tp{c['tp']} risk ${risk:.2f}")
            else:
                try:
                    if stop_entry:
                        broker.place_order("buy", sym, qty=qty, otype="stop", stop_price=entry, tif="gtc", cid=cid)
                    else:
                        # re-anchored marketable entries get a collar, not a naked market order:
                        # a limit a hair through the tape crosses but refuses to chase a gap.
                        lim = entry * (1 - 0.0015) if note else entry
                        broker.place_order("buy", sym, qty=qty, otype="limit", limit_price=lim, tif="gtc", cid=cid)
                    order_ok = True
                    journal(f"ORDER SENT — {sym} {c['skill']} (score {c['score']}/5) {'stop' if stop_entry else 'limit'} {c['otype']} qty {qty:.6f} @ {entry} sl{c['sl']} tp{c['tp']} · risk ${risk:.2f}")
                except broker.BrokerError as e:
                    order_ok = False
                    journal(f"ORDER FAILED — {sym} {c['skill']}: {e}")
            if order_ok:
                s["open_cids"][cid] = {"sym": sym, "skill": c["skill"], "otype": c["otype"], "entry": entry,
                                       "sl": c["sl"], "tp": c["tp"], "qty": round(qty, 8), "r_dist": r_dist,
                                       "score": c["score"], "risk": risk}
                tl_log({"rid": rid, "sym": sym, "skill": c["skill"], "otype": c["otype"], "entry": c["entry"],
                        "sl": c["sl"], "tp": c["tp"], "score": c["score"], "risk": risk, "fired": True})
                fired += 1
    eq = f" equity ${float(acct['equity']):.2f}" if acct else ""
    s["last_cycle"] = time.time()
    journal(f"scan ok · venue {VENUE} · {len(syms)} symbols · {fired} new · {len(s['open_cids'])} pendings · "
            f"{len(s['pos_state'])} positions{eq} · {int(time.time() - t0)}s")
    if EXEC_MODE == "coinbase" and not CB_KEYED:
        journal("NOTE — execution=coinbase but this runner has no COINBASE_API_KEY, so orders are "
                "being written to the SHADOW LEDGER (Coinbase public data, no real money). Add the "
                "Actions secret to trade the real book.")
    save_state(s)


def atr1h(sym, tf_map):
    return core.atr(tf_map[sym]["1h"]) or 0.0


def tl_update(sym, res, last, r_mult):
    rows = [json.loads(x) for x in open(TL_F) if x.strip()] if os.path.exists(TL_F) else []
    for row in reversed(rows):
        if row.get("sym") == sym and row.get("fired") and "result" not in row:
            row["result"] = res
            row["profit_ref"] = last
            row["R"] = r_mult
            break
    with open(TL_F, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def push_memory():
    """Write memory files back via the Contents API — no git rebases, no add/add
    conflicts. Append-only files get THIS run's lines; state files are last-writer-wins.
    409 (race) simply re-reads and retries."""
    import base64
    tok = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not (tok and repo):
        return
    api = f"https://api.github.com/repos/{repo}/contents/"
    hdr = {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"}

    def _http(url, req=None):
        try:
            with urllib.request.urlopen(req or urllib.request.Request(url, headers=hdr), timeout=20) as r:
                return json.loads(r.read()), r.status
        except urllib.error.HTTPError as e:
            return json.loads(e.read() or b"{}"), e.code

    def push(path, content, append):
        for _ in range(3):
            d, code = _http(api + path)
            if code == 404:
                sha, base = None, ""
            elif code == 200:
                sha, base = d.get("sha"), base64.b64decode(d.get("content", "")).decode()
            else:
                print(f"memory push {path}: read got {code}, retrying")
                continue
            body = json.dumps({
                "message": f"cycle {now().strftime('%m-%d %H:%M')} UTC",
                "content": base64.b64encode((base + content if append else content).encode()).decode(),
                **({"sha": sha} if sha else {})}).encode()
            req = urllib.request.Request(api + path, data=body, method="PUT",
                                         headers={**hdr, "Content-Type": "application/json"})
            _, code = _http(api + path, req)
            if code in (200, 201):
                print(f"memory push {path}: ok")
                return True
            print(f"memory push {path}: {code}, retrying")
        print(f"memory push {path}: FAILED after retries")
        return False

    if JOURNAL_LINES:
        push("journal.md", "\n".join(JOURNAL_LINES) + "\n", True)
    if TL_LINES:
        push("trades_log.jsonl", "\n".join(TL_LINES) + "\n", True)
    for f_ in ("state.json", "ledger.json"):
        p = os.path.join(HERE, f_)
        if os.path.exists(p):
            push(f_, open(p).read(), False)


if __name__ == "__main__":
    if EXEC_MODE == "alpaca" and not (os.environ.get("ALPACA_KEY_ID") and os.environ.get("ALPACA_SECRET")):
        fail("execution=alpaca but ALPACA_KEY_ID / ALPACA_SECRET missing — refusing to spin silently")
    if CB_KEYED and CFG.get("live_ack") is True and not (os.environ.get("COINBASE_API_SECRET")
                                                         or os.environ.get("COINBASE_CDP_PEM")):
        fail("execution=coinbase, live_ack=true, COINBASE_API_KEY set — but no COINBASE_API_SECRET "
             "(legacy key) or COINBASE_CDP_PEM (CDP key). A half-configured live venue is worse than none.")
    try:
        run()
    except SystemExit:
        raise
    except Exception as e:
        fail(f"cycle crash: {e!r}")
    push_memory()
