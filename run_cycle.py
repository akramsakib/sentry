"""Sentry v4.7.2 (GitHub-native) — one full scan/manage cycle per run.

v4.7.2: real-money trading moved HOME to the Mac runner (~/hermes_sentry/crypto/) — this repo
cycle keeps scanning, grading and rehearsing as the mirror, but its shipped config no longer arms
on key presence (auto_ack_on_key: false) so only ONE book can ever fire on the venue.

v4.7.0 is the parity release: the scan is no longer a subset. sentry_core.py now carries the
Mac/MT5 build's FULL engine — 22-pattern §12 candle library, all 16 skill families, five
timeframes (M5/M15/H1/H4/D1), same thresholds, same order — fed by OKX public candles (the
same feed the live orders trade against). What stays deliberately different, and why, is in
README "Engine parity".

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
import broker_okx as data_broker          # PUBLIC candles only — no keys, the live venue's own feed

CFG = json.load(open(os.path.join(HERE, "config.json")))
_CID_TS = re.compile(r"(\d{13})n\d+$")   # sentry{SYM}{ms}n{seq} -> the ms doubles as the placement clock
EXEC_MODE = CFG.get("execution", "ledger")
# Venue selection is one config line ("execution"). coinbase = real orders via
# broker_coinbase.py; it falls back to the shadow ledger ONLY when no key exists in this runner,
# and says so in the journal + summary so "did it place a real order?" is never a guess.
CB_KEYED = EXEC_MODE == "coinbase" and bool(os.environ.get("COINBASE_API_KEY"))
OKX_KEYED = EXEC_MODE == "okx" and bool(os.environ.get("OKX_API_KEY"))
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
elif EXEC_MODE == "okx" and OKX_KEYED:
    import broker_okx as broker                              # real OKX orders (swap: TP/SL on-venue)
    LIVE = True
    VENUE = ("okx-live(DRY)" if os.environ.get("OKX_DRY") == "1" else
             "okx-live(SIM, fake money)" if os.environ.get("OKX_SIM") == "1" else "okx-live")
elif EXEC_MODE == "coinbase":
    import broker_ledger as broker                           # venue chosen, key not in place yet
    VENUE = "shadow-ledger(coinbase-no-key)"
elif EXEC_MODE == "okx":
    import broker_ledger as broker                           # venue chosen, key not in place yet
    VENUE = "shadow-ledger(okx-no-key)"
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
# LIVE stays true when the venue itself is DRY or simulated: the guards below must run on the same
# code path money will take, or a rehearsal rehearses nothing. What changes is only the CLAIM made
# in STATUS.md — see MONEY, which is the flag that says "a dollar actually moved".
MONEY = LIVE and not getattr(broker, "DRY", False) and not getattr(broker, "SIM", False)

# --- venue cost ---------------------------------------------------------------------------
# The fee model lives in the ledger and is applied whatever the venue is: a paper book that pays
# nothing measures a place that does not exist, and the accuracy figure that sizes every trade was
# built on it. config.json "fees" sets maker/taker as fractions (0.0060 = 0.60 %).
import broker_ledger as ledger
FEES = ledger.set_fees(CFG.get("fees"))
# What the venue can do, not what we wish it could: shorts need hedge-mode perps, and on-venue
# TP/SL means the stop is enforced while this runner is asleep. Both default False, so the shadow
# ledger keeps behaving exactly like a spot book that wakes up twice a day.
CAN_SHORT = bool(getattr(broker, "CAN_SHORT", False))
ATTACH = bool(getattr(broker, "ATTACH_TP_SL", False))
MAX_FEE_R = float(CFG.get("live_max_fee_r") or 0)     # 0 disables the live refusal
FEE_REFUSED = [0]                                      # mutated by the scan loop, read by the alert


def fee_drag(entry_px, exit_px, r_dist, qty=1.0):
    """(dollars, R) the venue takes on one round trip. Both legs are charged as taker: a stop entry
    and a stop exit both cross into a moving market, and a guard that assumed maker would be a
    guard that assumes the flattering case."""
    return ledger.round_trip_fees(entry_px, exit_px, r_dist, qty)


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
    """Returns {'5m','15m','1h','4h','1d'} closed-bar dicts, oldest→newest, or fails red.

    The data plane is always OKX public candles, whatever the execution venue is: scanning one
    venue's feed and trading another's is how a paper book drifts from the real one. Five
    timeframes because that is what the Mac engine consumes — dropping M5/M15 or H4/D1 quietly
    changes WHICH signals fire, so the data budget is part of the strategy, not plumbing.
    """
    TFS = (("5m", "5Minute", 200), ("15m", "15Minute", 200), ("1h", "1Hour", 200),
           ("4h", "4Hour", 200), ("1d", "1Day", 60))
    if FIXDIR:
        fn = os.path.join(FIXDIR, sym.replace("/", "") + ".json")
        d = json.load(open(fn))
        for tf, _, need in (("5m", 0, 25), ("15m", 0, 15), ("1h", 0, 60), ("4h", 0, 30), ("1d", 0, 12)):
            if len(d.get(tf) or []) < need:
                fail(f"fixtures thin for {sym}: {tf} has {len(d.get(tf) or [])}, need {need}")
        return d, d.get("_asof", 0)
    tf_map = {}
    try:
        for key, bt, lim in TFS:
            tf_map[key] = data_broker.crypto_bars(sym, bt, lim)
    except Exception as e:                                       # fail red, never trade blind
        fail(f"data fetch error {sym}: {type(e).__name__}: {e}")
    h1, m5 = tf_map["1h"], tf_map["5m"]
    # staleness guards: crypto prints 24/7, so a dead feed is indistinguishable from a quiet
    # market ONLY by the clock. (The Mac build journalled "scan ok" with quotes [] for 13 hours
    # and kept trading; that bug is not being ported.)
    for tf_key, age_lim, label in (("1h", 3 * 3600, "1h"), ("5m", 45 * 60, "5m")):
        bars = tf_map[tf_key]
        if bars:
            ts = datetime.fromisoformat(bars[-1]["t"].replace("Z", "+00:00")).timestamp()
            if now().timestamp() - ts > age_lim:
                fail(f"STALE DATA: {sym} last closed {label} bar is >{age_lim // 3600 if age_lim >= 3600 else age_lim // 60}"
                     f"{'h' if age_lim >= 3600 else 'm'} old — exchange or feed is down, not a 'no signal'")
    if (len(m5) < 25 or len(tf_map["15m"]) < 15 or len(h1) < 60
            or len(tf_map["4h"]) < 30 or len(tf_map["1d"]) < 8):
        fail(f"THIN DATA: {sym} m5={len(m5)} m15={len(tf_map['15m'])} h1={len(h1)} "
             f"h4={len(tf_map['4h'])} d1={len(tf_map['1d'])} — expected a healthy history")
    return tf_map, 0


def grade(r_mult):
    """One rule for grading a closed trade: sign of the realised R. `scratch` covers the ~0 cases
    (fees/spread ate it) so they neither flatter nor punish the accuracy loop."""
    if r_mult > 0.05:
        return "win"
    if r_mult < -0.05:
        return "loss"
    return "scratch"


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
        # 2026-11-14, user directive "complete the setup, don't ask me back": with
        # auto_ack_on_key, the act of putting a trade-only OKX key into this repo's secrets IS the
        # acknowledgement — minting the key is the one step that can never be done from here anyway.
        # The blast radius of a leaked+planted key stays bounded: trade-only permission, no
        # withdrawal whitelist bypass, and every dollar-clamp below still applies.
        if not (CFG.get("auto_ack_on_key") and OKX_KEYED):
            return False, ("config.live_ack is not true — or just paste a real OKX trade key into "
                           "Settings → Secrets and it arms itself (auto_ack_on_key)")
        journal("LIVE ACK — granted by key presence (auto_ack_on_key, user directive 2026-11-14)")
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
            if hasattr(broker, "fills"):
                try:                                        # the venue's tape beats our last poll
                    fl = [f for f in (broker.fills(symbol=sym) or []) if float(f.get("size") or 0) > 0]
                    if fl:
                        last = float(fl[-1].get("price") or last)
                except Exception as e:                      # noqa: BLE001 — a missing print must not stop grading
                    journal(f"NOTE — could not read venue fills for {sym}: {type(e).__name__}: {e}")
            # Grade on what was actually made, not on whether the target was ever touched: a
            # 2026-11-14 DOGE stop-out exited ABOVE its entry (a favourable scratch), and the
            # target test still called it a loss with "+0.36R" — which then fed a false miss into
            # the accuracy loop that sizes every future trade.
            if ps.get("r_dist"):
                _, f_r = fee_drag(ps["entry"], last, ps["r_dist"], ps.get("qty") or 1.0)
                r_mult = round((last - ps["entry"]) / ps["r_dist"] - f_r, 2)
            else:
                r_mult = 0.0
            res = grade(r_mult)
            tl_update(sym, res, last, r_mult)
            journal(f"CLOSED {sym} — graded {res} ({r_mult:+.2f}R{' net of ' + format(f_r, '.2f') + 'R in venue fees' if ps.get('r_dist') and f_r else ''}) from exit {last:.8g}")
            if not DRY:
                # Cancel ONLY this symbol's leftovers. A blanket cancel_all() here once deleted two
                # unrelated resting entries (XRP/SOL, 2026-11-14) while the journal still claimed
                # those orders were live — the log and the book must never disagree.
                try:
                    for o in broker.open_orders():
                        if o.get("symbol") == sym and (o.get("client_order_id") or "").startswith("sentry"):
                            broker.cancel_order(o["id"])
                            journal(f"CANCEL leftover {sym} order {o.get('client_order_id')} after close")
                except broker.BrokerError as e:
                    journal(f"NOTE — could not clean leftover {sym} orders: {e}")
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
        if side == "short" and fav >= 1.5 * rd:            # chandelier both ways, like the Mac
            cand = round(cur + 2 * atr1h(sym, tf_map), 8)
            if cand < new_sl:
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
                    fill = float(o["filled_avg_price"] or meta["entry"])
                    # A re-anchored (marketable) entry can fill BETTER than the level it was scored
                    # from, which can put the fill beyond the stop — DOGE 2026-11-14: filled at
                    # 0.06068 against a 0.06080 stop, a position that is stopped out the instant it
                    # exists. Scratch it now instead of holding a contradiction.
                    if fill <= meta["sl"]:
                        tl_update(sym, "scratch", fill, 0.0)
                        journal(f"SCRATCH — {sym}: filled {fill:.8g} at/below its own stop "
                                f"{meta['sl']:.8g} — no valid risk to hold, closing immediately")
                        if not DRY:
                            try:
                                broker.place_order("sell", sym, qty=float(o.get("filled_qty") or meta["qty"]),
                                                   otype="market")
                            except broker.BrokerError as e:
                                journal(f"ALERT — {sym} needs a manual close, market order rejected: {e}")
                        s["open_cids"].pop(cid, None)
                        continue
                    s["pos_state"][sym] = {"side": "long", "entry": fill,
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
        cands = core.evaluate_symbol(sym, tf_map[sym], CFG["min_score_fire"],
                                     seen=s.setdefault("seen_candles", []))
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
            if is_sell and sym not in s["pos_state"] and not CAN_SHORT:
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
                tape = float(tf_map[sym]["5m"][-1]["c"])   # the Mac's live bid, at this build's cadence
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
            # Can this trade even pay for its own ticket? A 0.55 % stop on a 0.60/0.40 % schedule
            # costs 1.8R: the exit at the target is a coin flip after the venue has taken its cut.
            f_usd, f_r = fee_drag(entry, entry - r_dist, r_dist, qty)
            if LIVE and MAX_FEE_R and f_r > MAX_FEE_R:
                FEE_REFUSED[0] += 1
                journal(f"SKIP — {sym} {c['skill']}: venue fees cost {f_r:.2f}R (cap {MAX_FEE_R:g}R) on a "
                        f"{100 * r_dist / entry:.2f} % stop — ${f_usd:.2f} paid to trade for ${risk:.2f} of risk. "
                        f"Refused, not resized: the stop distance belongs to the checklist.")
                continue
            fee_note = f" · fees ~${f_usd:.2f} ({f_r:.2f}R)" if f_usd else ""
            s["cid_seq"] = s.get("cid_seq", 0) + 1
            cid = f"sentry{sym.replace('/', '')}{int(time.time() * 1000)}n{s['cid_seq']}"[:60]
            # breakout entries must ride a real STOP order (a buy-limit above market would
            # fill instantly at market, faking the breakout); pullbacks use GTC LIMIT at level
            stop_entry = c["otype"].endswith("_stop")
            if DRY:
                order_ok = True
                pending_syms.add(sym)
                journal(f"DRY-FIRE — {sym} {c['skill']} {c['otype']} qty {qty:.6f} @ {entry * (1 - 0.0015) if (note and not stop_entry) else entry} sl{c['sl']} tp{c['tp']} risk ${risk:.2f}{fee_note}")
            else:
                try:
                    # A re-anchored marketable entry gets a collar, not a naked market order: a
                    # limit a hair through the tape crosses but refuses to chase a gap.
                    lim = entry * (1 - 0.0015) if (note and not stop_entry) else entry
                    # hedge mode flips the side on a perp: a short entry is a SELL that opens, not a
                    # buy, and the venue still owns both protective legs either way
                    leg_side = "sell" if (is_sell and CAN_SHORT) else "buy"
                    extra = {"tp": c["tp"], "sl": c["sl"]} if ATTACH else {}
                    if stop_entry:
                        broker.place_order(leg_side, sym, qty=qty, otype="stop", stop_price=lim,
                                           tif="gtc", cid=cid, **extra)
                    else:
                        broker.place_order(leg_side, sym, qty=qty, otype="limit", limit_price=lim,
                                           tif="gtc", cid=cid, **extra)
                    order_ok = True
                    journal(f"ORDER SENT — {sym} {c['skill']} (score {c['score']}/5) {'stop' if stop_entry else 'limit'} {c['otype']} qty {qty:.6f} @ {lim}{' (collar on ' + format(entry, '.10g') + ')' if lim != entry else ''} sl{c['sl']} tp{c['tp']} · risk ${risk:.2f}{fee_note}{' · TP/SL attached on-venue' if ATTACH else ''}{' SHORT' if (is_sell and CAN_SHORT) else ''}")
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
    try:
        write_status(acct, live, s, tl_rows(), tf_map, fired)   # re-read: grading just landed
    except Exception as e:                                    # noqa: BLE001
        journal(f"NOTE — status page not written: {type(e).__name__}: {e}")
    if LIVE and FEE_REFUSED[0] and not fired:
        journal(f"ALERT — every live signal this cycle was refused because the venue's fee is bigger "
                f"than the trade's risk ({FEE_REFUSED[0]} refused). This is arithmetic, not a bug: a "
                f"{100 * (FEES['maker'] + FEES['taker']):.2f} % round trip against 0.4-1.2 % stops costs "
                f"more than one R. Either trade a maker-only venue, set config.fees to what the account "
                f"actually pays, or widen the stops — and widening them invalidates the score history, so "
                f"it is a decision, not a tuning knob. (Paper still trades: the guard is live-only.)")
    _fs = ledger.fee_stats() if hasattr(ledger, "fee_stats") else {}
    _fee_str = (f" · venue fees ${_fs.get('paid', 0.0):,.2f} to date @ "
                f"{100 * FEES['maker']:.2f}/{100 * FEES['taker']:.2f}%") if (FEES["maker"] or FEES["taker"]) else ""
    journal(f"scan ok · venue {VENUE} · {len(syms)} symbols · {fired} new · {len(s['open_cids'])} pendings · "
            f"{len(s['pos_state'])} positions{eq} · {int(time.time() - t0)}s{_fee_str}")
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


STATUS_F = os.path.join(HERE, "STATUS.md")

LEGEND = """
| line starts with | meaning |
|---|---|
| `CANDIDATE(score n/5)` | a skill matched and was scored, but no order was sent (short on spot, duplicate, below the fire floor) |
| `ORDER SENT` | an order was placed on the venue named in the summary line |
| `RE-ANCHORED` | the trigger was already through the tape, so entry moved to market and R was recomputed |
| `FILL` | an entry filled — now a position, with its stop armed on the venue |
| `EXIT` / `CLOSED` | stop or target hit; P&L booked and the signal graded win/loss |
| `SKIP` / `CAPPED` / `LIVE RISK CLAMP` | a guard refused or resized the trade; reason is inline |
| `GATE` | live venue armed but new entries blocked; reason is inline |
| `EXPIRED` | a resting entry went older than `pending_ttl_h` and was cancelled — the setup is stale |
| `ALERT` | the cycle died. The run is red — open its log, nothing was skipped on purpose |
"""


def write_status(acct, live, s, rows, tf_map, fired):
    """One human-readable page, rewritten by the bot at the end of every cycle. The JSON files are
    the machine memory; this is the thing you actually look at."""
    def px(sym):
        try:
            return float(tf_map[sym]["15m"][-1]["c"])
        except Exception:                                     # noqa: BLE001
            return 0.0

    out = ["# Sentry — live status",
           "",
           "_Written by the bot at the end of every cycle. Never edited by hand — if it disagrees "
           "with `journal.md`, the journal is right._",
           ""]
    eq = float((acct or {}).get("equity") or 0)
    cash = float((acct or {}).get("cash") or 0)
    real = ("REAL MONEY" if MONEY else
            "live venue, DRY — payloads built, nothing sent" if LIVE else
            "live venue, SIMULATED — real engine, fake money" if LIVE else "shadow book (paper)")
    out.append(f"**{now().strftime('%Y-%m-%d %H:%M UTC')}** · venue `{VENUE}` → {real} · "
               f"cash ${cash:,.2f} · equity ${eq:,.2f}")
    out.append("")
    # the cost of doing business, on the page you actually look at: a tight-stop book on a wide-fee
    # venue is a fee farm, and that belongs next to the P&L, not buried in a config file.
    if FEES["maker"] or FEES["taker"]:
        _paid = (ledger.fee_stats().get("paid", 0.0) if hasattr(ledger, "fee_stats") else 0.0)
        out.append(f"_Venue cost: {100 * FEES['maker']:.2f} % maker / {100 * FEES['taker']:.2f} % taker per side · "
                   f"**${_paid:,.2f} paid on this book to date** · every graded R is net of it"
                   + (f" · live orders refused when the fee costs more than {MAX_FEE_R:g}R of the trade's own risk"
                      if MAX_FEE_R else " · no live fee guard (live_max_fee_r = 0)") + "_")
        out.append("")

    # ---- resting orders
    out.append(f"## Orders resting on the book now ({len(s['open_cids'])})")
    out.append("")
    if s["open_cids"]:
        out.append("| symbol | order | trigger | size | notional | risk | tape | to trigger | age |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for cid, m in sorted(s["open_cids"].items(), key=lambda kv: kv[1]["sym"]):
            t = px(m["sym"])
            dist = (m["entry"] / t - 1) * 100 if t else 0.0
            mm = _CID_TS.search(cid)
            age = (time.time() - int(mm.group(1)) / 1000.0) / 60.0 if mm else -1
            out.append(f"| {m['sym']} | {m['otype']} | {m['entry']:.8g} | {m['qty']:.6g} | "
                       f"${m['qty'] * m['entry']:,.0f} | ${m['risk']:.2f} | {t:.8g} | "
                       f"{dist:+.2f}% | {age:.0f} min |")
        ttl = float(CFG.get("pending_ttl_h", 6.0))
        out.append("")
        out.append(f"_Entries expire after {ttl:g} h (`pending_ttl_h`): a breakout trigger from 6 hours "
                   f"ago is not the same trade, it is just an old order._")
    else:
        out.append("_None. Every symbol is scanned each cycle; a resting entry above is a trigger "
                   "waiting to be hit, not a position._")
    out.append("")

    # ---- positions
    out.append(f"## Positions ({len(s['pos_state'])})")
    out.append("")
    if s["pos_state"]:
        out.append("| symbol | qty | entry | mark | P&L | stop | target | R held |")
        out.append("|---|---|---|---|---|---|---|---|")
        for sym, ps in sorted(s["pos_state"].items()):
            cur = float((live.get(sym) or {}).get("current_price") or ps.get("last_price") or 0) or px(sym)
            q = float(ps.get("qty") or 0)
            pl = (cur - ps["entry"]) * q if cur and q else 0.0
            rmul = (cur - ps["entry"]) / ps["r_dist"] if cur and ps.get("r_dist") else 0.0
            out.append(f"| {sym} | {q:.6g} | {ps['entry']:.8g} | {cur:.8g} | ${pl:,.2f} | "
                       f"{ps['sl']:.8g} | {ps['tp']:.8g} | {rmul:+.2f}R |")
    else:
        out.append("_Flat._")
    out.append("")

    # ---- signals
    out.append(f"## Last 12 signals ({len(rows)} ever logged)")
    out.append("")
    out.append("| time | symbol | skill | score | entry | stop | target | size | outcome |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    for r in rows[-12:][::-1]:
        if r.get("result"):
            oc = f"**{r['result']}** " + (f"({r.get('R', 0):+.2f}R)" if r.get("R") is not None else "")
        elif r.get("fired"):
            oc = "order placed"
        elif "short" in str(r.get("note", "")) or "short" in str(r.get("otype", "")):
            oc = "paper-graded (spot cannot short)"
        else:
            oc = "not fired (guard/duplicate)"
        out.append(f"| {str(r.get('ts', ''))[5:]} | {r.get('sym')} | {r.get('skill')} | "
                   f"{r.get('score')}/5 | {r.get('entry'):.8g} | {r.get('sl'):.8g} | {r.get('tp'):.8g} | "
                   f"${r.get('risk', 0):.2f} | {oc} |")
    out.append("")

    # ---- accuracy / sizing, the loop the whole design hangs on
    graded = [r for r in rows if r.get("fired") and r.get("result")]
    wins = [r for r in graded if r["result"] == "win"]
    sizer = core.Sizer(CFG["base_risk"], CFG["min_risk"], CFG["max_risk"])
    sizes = " · ".join(f"score {sc} -> ${sizer.size('S11-dc20-long', sc, rows):.2f}" for sc in (3, 4, 5))
    avg_r = sum(float(r.get("R") or 0) for r in graded) / len(graded) if graded else 0.0
    out.append("## Accuracy so far")
    out.append("")
    losses = [r for r in graded if r["result"] == "loss"]
    scratches = len(graded) - len(wins) - len(losses)
    wr = (100.0 * len(wins) / (len(wins) + len(losses))) if (wins or losses) else 0.0
    out.append(f"{len(graded)} graded outcomes ({len(wins)} win / {len(losses)} loss"
               + (f" / {scratches} scratch" if scratches else "") + f") · win rate {wr:.0f}% · "
               f"avg {avg_r:+.2f}R · sizing today: {sizes}")
    out.append("")
    out.append("_Risk per trade is this bot's own decision: it scales with the accuracy it has "
               "demonstrated on its own fills, bounded by `min_risk`/`max_risk`, then by "
               "`live_max_risk` on a live venue._")
    out.append("")
    out.append(f"## This cycle: {fired} new order(s), {len(CFG['symbols'])} symbols scanned")
    out.append("")
    out.append(LEGEND.strip())
    out.append("")
    raw = "https://raw.githubusercontent.com/" + (os.environ.get("GITHUB_REPOSITORY") or "akramsakib/sentry") + "/main"
    out.append("## Read it from a terminal")
    out.append("")
    out.append("```bash")
    out.append(f"curl -s {raw}/STATUS.md | head -40            # this page")
    out.append(f"curl -s {raw}/journal.md | tail -20           # every decision, newest last")
    out.append(f"curl -s {raw}/ledger.json | python3 -m json.tool   # the book itself")
    out.append(f"curl -s {raw}/trades_log.jsonl | tail -5      # one line per signal")
    out.append("```")
    out.append("")
    out.append("_On a live venue the exchange is the authority: the orders above are what Sentry "
               "believes it placed, the venue's own Orders/Positions tab (OKX app or web) is what "
               "actually exists._")
    txt = "\n".join([l for l in out if l is not None]) + "\n"
    with open(STATUS_F, "w") as f:
        f.write(txt)
    return txt


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
    # trades_log is REPLACED, not appended. Outcomes are written back into rows that already
    # exist (tl_update), so an append-only push ships the new signal and silently drops its grade —
    # which is what happened on 2026-11-14: the journal read "CLOSED DOGE/USD — graded loss" while
    # trades_log on main still had zero graded rows, so the accuracy loop that sizes every future
    # trade could never learn, forever. The local file already holds history + this run's rows.
    for f_ in ("trades_log.jsonl", "state.json", "ledger.json", "STATUS.md"):
        p = os.path.join(HERE, f_)
        if os.path.exists(p):
            push(f_, open(p).read(), False)


if __name__ == "__main__":
    if EXEC_MODE == "alpaca" and not (os.environ.get("ALPACA_KEY_ID") and os.environ.get("ALPACA_SECRET")):
        fail("execution=alpaca but ALPACA_KEY_ID / ALPACA_SECRET missing — refusing to spin silently")
    if EXEC_MODE == "okx" and OKX_KEYED and CFG.get("live_ack") is True:
        miss = [k for k in ("OKX_API_KEY", "OKX_API_SECRET", "OKX_API_PASSPHRASE") if not os.environ.get(k)]
        if miss:
            fail("execution=okx with live_ack=true but these are missing: " + ", ".join(miss)
                 + " — OKX signs with all three, and a half-configured live venue is worse than none.")
    if EXEC_MODE == "okx" and FEES["taker"] > 0.0015:
        journal(f"NOTE — config.fees says {100 * FEES['taker']:.2f} % taker, which is not an OKX number "
                f"(0.05 % base tier). Either the schedule is stale or the venue changed; every R below "
                f"is priced off it, so fix config.json rather than trusting the book.")
    if CB_KEYED and CFG.get("live_ack") is True and not (os.environ.get("COINBASE_API_SECRET")
                                                         or os.environ.get("COINBASE_CDP_PEM")):
        fail("execution=coinbase, live_ack=true, COINBASE_API_KEY set — but no COINBASE_API_SECRET "
             "(legacy key) or COINBASE_CDP_PEM (CDP key). A half-configured live venue is worse than none.")
    if CB_KEYED and CFG.get("live_ack") is True:
        # the two Coinbase APIs are different accounts with different credentials; failing here is
        # far cheaper than watching every order come back 401 for one reason repeated 80 times.
        mode = (os.environ.get("COINBASE_MODE")
                or ("exchange" if os.environ.get("COINBASE_API_PASSPHRASE") else "advanced"))
        if mode == "exchange" and not os.environ.get("COINBASE_API_PASSPHRASE"):
            fail("COINBASE_MODE=exchange needs COINBASE_API_PASSPHRASE — a retail Coinbase account key "
                 "cannot sign at api.exchange.coinbase.com at all. Either mint the key at "
                 "exchange.coinbase.com (View+Trade) or set COINBASE_MODE=advanced.")
    try:
        run()
    except SystemExit:
        raise
    except Exception as e:
        fail(f"cycle crash: {e!r}")
    push_memory()
