"""What a resident book publishes about itself, for the desk monitor.

crypto_loop.py calls publish() after every cycle. It writes ONE small JSON into
~/hermes_sentry/books/<folder>.json, atomically (tmp + os.replace), because the monitor reads it while
the book is mid-write a hundred times a day and a half-written file on a dashboard reads as a crash.

Why a file per book instead of the monitor parsing three journals: the journal is a log, and turning a
log into state on every read is how a display starts lying the day the log format drifts. The book
already knows the truth — positions, pendings, what it is blocked on — so the book says it.

Nothing here trades or sends. Read-only over the book's own files, and every accessor tolerates a
missing/corrupt file, because a monitor must never be the reason a book stops.
"""
import json
import os
import time

KL_OFFSET = 8 * 3600                     # Kuala Lumpur, the timezone the desk runs on
EVENT_MARKS = ("ORDER SENT", "FILL", "CLOSED", "LIVE ACK", "ALERT", "GATE", "WIDENED",
               "SCRATCH", "CAPPED", "CANCEL", "REAL MONEY", "STALE DATA")


def kl(ts=None):
    return time.strftime("%Y-%m-%d %H:%M KL", time.gmtime((ts or time.time()) + KL_OFFSET))


def _json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _lines(path):
    try:
        with open(path, errors="replace") as f:
            return f.read().splitlines()
    except Exception:
        return []


def _num(v, dflt=0.0):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return dflt
    return f if f == f else dflt          # NaN-safe: a NaN on a dashboard reads as a bug in the bot


def _events(here, n=8):
    out = []
    for ln in _lines(os.path.join(here, "journal.md"))[-400:]:
        body = ln.split("**", 2)[-1].strip() if "**" in ln else ln.strip("- ").strip()
        if body and any(m in body for m in EVENT_MARKS):
            out.append(body[:220])
    return out[-n:][::-1]


def _positions(state, ledger):
    """Open positions with the thing a desk actually needs: how far from the stop, in R."""
    pos = state.get("pos_state") or {}
    rows = []
    for sym, p in pos.items():
        entry = _num(p.get("entry"))
        sl = _num(p.get("sl"))
        tp = _num(p.get("tp"))
        last = _num(p.get("last_price")) or entry
        r_dist = _num(p.get("r_dist")) or abs(entry - sl)
        side = p.get("side") or "long"
        sgn = 1.0 if side == "long" else -1.0
        r_live = ((last - entry) * sgn / r_dist) if r_dist else 0.0
        rows.append({
            "sym": sym, "side": side, "skill": p.get("skill") or "",
            "qty": _num(p.get("qty")), "entry": entry, "last": last, "sl": sl, "tp": tp,
            "notional": round(_num(p.get("qty")) * last, 2),
            "r_live": round(r_live, 3),
            "r_to_stop": round(r_dist and (last - sl) / r_dist or 0.0, 2) if side == "long"
                         else round(r_dist and (sl - last) / r_dist or 0.0, 2),
            "r_to_target": round(((tp - last) / r_dist), 2) if r_dist and tp else None,
            "pnl": round((last - entry) * _num(p.get("qty")) * sgn, 2),
            "breakeven_at": p.get("be"),
        })
    rows.sort(key=lambda x: -abs(x["notional"]))
    return rows


def _pendings(state):
    rows = []
    for cid, o in (state.get("open_cids") or {}).items():
        rows.append({"sym": o.get("sym"), "skill": o.get("skill"), "type": o.get("otype"),
                     "entry": _num(o.get("entry")), "sl": _num(o.get("sl")), "tp": _num(o.get("tp")),
                     "score": o.get("score"), "risk": _num(o.get("risk")),
                     "qty": _num(o.get("qty")),
                     "notional": round(_num(o.get("qty")) * _num(o.get("entry")), 2)})
    rows.sort(key=lambda x: -(x.get("score") or 0))
    return rows


def _grades(here):
    rows = []
    for ln in _lines(os.path.join(here, "trades_log.jsonl")):
        try:
            rows.append(json.loads(ln))
        except Exception:
            pass
    g = [r for r in rows if r.get("result")]
    wins = sum(1 for r in g if r["result"] == "win")
    losses = sum(1 for r in g if r["result"] == "loss")
    scratch = len(g) - wins - losses
    rsum = sum(_num(r.get("R")) for r in g)
    per = {}
    for r in g:
        k = r.get("skill") or "?"
        w = 1.0 if r["result"] == "win" else (0.5 if r["result"] == "scratch" else 0.0)
        a = per.setdefault(k, [0.0, 0.0])
        a[0] += w
        a[1] += 1
    skills = sorted(({"skill": k, "acc": round(v[0] / v[1], 3), "n": v[1]}
                     for k, v in per.items() if v[1] >= 3), key=lambda x: -x["acc"])
    return {"log_rows": len(rows), "graded": len(g), "wins": wins, "losses": losses,
            "scratch": scratch, "net_r": round(rsum, 2),
            "hit_rate": round(wins / len(g), 3) if g else None,
            "fired": sum(1 for r in rows if r.get("fired")),
            "by_skill": skills[:6],
            "note": ("no graded history yet — the sizer uses the neutral prior and grows from here"
                     if not g else "sizer is reading this book's own outcomes")}


def book_status(here, extra=None):
    cfg = _json(os.path.join(here, "config.json"), {})
    led = _json(os.path.join(here, "ledger.json"), {})
    st = _json(os.path.join(here, "state.json"), {})
    fees = cfg.get("fees") or {}
    mk, tk = _num(fees.get("maker")), _num(fees.get("taker"))
    stop = max(_num(cfg.get("stop_floor_frac")), 0.005)
    drag = round(2 * tk / stop, 3) if tk and stop else None        # what the live guard computes
    cap = _num(cfg.get("live_max_fee_r"), 0.25)
    positions = _positions(st, led)
    pendings = _pendings(st)
    eq = _num(led.get("cash")) + sum(p["notional"] for p in positions)
    err_f = os.path.join(here, "crypto.err.log")
    out = {
        "updated": kl(),
        "updated_ts": time.time(),          # the monitor needs an AGE, not a pretty stamp
        "book": os.path.basename(here.rstrip("/")),
        "folder": here,
        "execution": cfg.get("execution"),
        "venue": (extra or {}).get("venue") or cfg.get("execution"),
        "state": (extra or {}).get("state") or "shadow",
        "money": bool((extra or {}).get("money")),
        "key_file": (extra or {}).get("key_file") or "",
        "cycle_s": (extra or {}).get("cycle_s"),
        "equity": round(eq, 2),
        "cash": round(_num(led.get("cash")), 2),
        "realized": round(_num(led.get("realized")), 2),
        "fees_paid": round(_num(led.get("fees_paid")), 2),
        "n_positions": len(positions),
        "n_pendings": len(pendings),
        "exposure": round(sum(p["notional"] for p in positions), 2),
        "at_risk": round(sum(_num(p["risk"]) * 1.0 for p in pendings), 2),
        "positions": positions,
        "pendings": pendings,
        "sizing": {"base_risk": _num(cfg.get("base_risk")), "min": _num(cfg.get("min_risk")),
                   "max": _num(cfg.get("max_risk")), "live_max_risk": _num(cfg.get("live_max_risk")),
                   "live_max_risk_frac": cfg.get("live_max_risk_frac"),
                   "max_notional_frac": cfg.get("max_notional_frac"),
                   "min_stop_frac": cfg.get("min_stop_frac"),
                   "stop_floor_frac": _num(cfg.get("stop_floor_frac"))},
        "cost": {"maker": mk, "taker": tk, "stop_frac": stop, "drag_r": drag, "cap_r": cap,
                 "verdict": ("inside cap" if drag is not None and drag <= cap else
                             "OVER CAP — live signals will be refused" if drag is not None else "unknown")},
        "grades": _grades(here),
        "auto_ack_on_key": bool(cfg.get("auto_ack_on_key")),
        "live_ack": cfg.get("live_ack"),
        "blocked_on": (extra or {}).get("blocked_on") or [],
        "events": _events(here),
        "last_scan": (next((l for l in reversed(_lines(os.path.join(here, "journal.md")))
                            if "scan ok" in l), "")).split("**")[-1].strip()[:200],
        "err_bytes": os.path.getsize(err_f) if os.path.exists(err_f) else 0,
        "config_note": (cfg.get("note") or "")[:400],
    }
    return out


def publish(here, root, extra=None):
    """Write this book's status file. Never raises: a monitor that can break a cycle is not a monitor."""
    try:
        data = book_status(here, extra)
        d = os.path.join(root, "books")
        os.makedirs(d, exist_ok=True)
        dst = os.path.join(d, data["book"] + ".json")
        tmp = dst + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=1, sort_keys=False)
            f.write("\n")
        os.replace(tmp, dst)                      # atomic: the monitor never sees a partial file
        return dst
    except Exception as e:                        # noqa: BLE001
        try:
            with open(os.path.join(here, "journal.md"), "a") as f:
                f.write("- **%s** NOTE — status publish skipped: %s: %s\n" % (kl(), type(e).__name__, e))
        except Exception:
            pass
        return None
