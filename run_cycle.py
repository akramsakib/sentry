"""Sentry v4 (GitHub-native) — one full scan/manage cycle per run.

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
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import sentry_core as core

CFG = json.load(open(os.path.join(HERE, "config.json")))
EXEC_MODE = CFG.get("execution", "ledger")
if EXEC_MODE == "alpaca":
    import broker
else:
    import broker_ledger as broker
STATE_F = os.path.join(HERE, "state.json")
JOURNAL_F = os.path.join(HERE, "journal.md")
TL_F = os.path.join(HERE, "trades_log.jsonl")
FIXDIR = os.environ.get("SENTRY_FIXTURES")
DRY = bool(FIXDIR) or os.environ.get("SENTRY_DRY") == "1"


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
    fired = 0
    for sym in syms:
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
            r_dist = abs(c["entry"] - c["sl"])
            qty = risk / r_dist
            if c["entry"] * qty < CFG["min_notional"]:
                journal(f"SKIP — {sym} {c['skill']}: qty below min notional (risk ${risk} too small for ${c['entry']:.2f} price)")
                continue
            s["cid_seq"] = s.get("cid_seq", 0) + 1
            cid = f"sentry{sym.replace('/', '')}{int(time.time() * 1000)}n{s['cid_seq']}"[:60]
            # breakout entries must ride a real STOP order (a buy-limit above market would
            # fill instantly at market, faking the breakout); pullbacks use GTC LIMIT at level
            stop_entry = c["otype"].endswith("_stop")
            if DRY:
                order_ok = True
                pending_syms.add(sym)
                journal(f"DRY-FIRE — {sym} {c['skill']} {c['otype']} qty {qty:.6f} @ {c['entry']} sl{c['sl']} tp{c['tp']} risk ${risk}")
            else:
                try:
                    if stop_entry:
                        broker.place_order("buy", sym, qty=qty, otype="stop", stop_price=c["entry"], tif="gtc", cid=cid)
                    else:
                        broker.place_order("buy", sym, qty=qty, otype="limit", limit_price=c["entry"], tif="gtc", cid=cid)
                    order_ok = True
                    journal(f"ORDER SENT — {sym} {c['skill']} (score {c['score']}/5) {'stop' if stop_entry else 'limit'} {c['otype']} qty {qty:.6f} @ {c['entry']} sl{c['sl']} tp{c['tp']} · risk ${risk}")
                except broker.BrokerError as e:
                    order_ok = False
                    journal(f"ORDER FAILED — {sym} {c['skill']}: {e}")
            if order_ok:
                s["open_cids"][cid] = {"sym": sym, "skill": c["skill"], "otype": c["otype"], "entry": c["entry"],
                                       "sl": c["sl"], "tp": c["tp"], "qty": round(qty, 8), "r_dist": r_dist,
                                       "score": c["score"], "risk": risk}
                tl_log({"rid": rid, "sym": sym, "skill": c["skill"], "otype": c["otype"], "entry": c["entry"],
                        "sl": c["sl"], "tp": c["tp"], "score": c["score"], "risk": risk, "fired": True})
                fired += 1
    eq = f" equity ${float(acct['equity']):.2f}" if acct else ""
    journal(f"scan ok · {len(syms)} symbols · {fired} new · {len(s['open_cids'])} pendings · "
            f"{len(s['pos_state'])} positions{eq} · {int(time.time() - t0)}s")
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
    try:
        run()
    except SystemExit:
        raise
    except Exception as e:
        fail(f"cycle crash: {e!r}")
    push_memory()
