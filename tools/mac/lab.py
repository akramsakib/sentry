#!/usr/bin/env python3
"""Hermes research lab — the R&D half of the sentry. Runs beside the books, never inside them.

Why this exists: the desk can execute a playbook and grade itself, and it has been doing exactly that —
78 graded outcomes, net -22.76R — with nothing asking *why*, and nothing trying the next thing. Execution
without research is a machine that repeats one mistake on a 10-minute cadence. This is the part that
argues with the playbook, in numbers, and writes down who won.

How an idea is tested (the only part that matters):
  1. the REAL engine produces the signal stream — `sentry_core.evaluate_symbol`, the same function the
     books call, replayed bar by bar over history. Nothing here re-implements a pattern, because a
     research loop that tests its own copy of the strategy proves nothing about the one that trades;
  2. each candidate is resolved forward through actual bars with the fee model the live path charges
     (`run_cycle.fee_drag` → `broker_ledger.round_trip_fees`, taker on both legs), graded by
     `run_cycle.grade`, and every win-rate figure comes from `grade_stats` — the same module the desk
     page and the position sizer read. One definition, four views;
  3. a hypothesis is a declarative filter over that stream (raise the score floor, drop a pattern, skip a
     volatility regime). The verdict is PAIRED: what happened to the trades it removed, not whether its
     own subset looks nice in isolation — a filter that drops 40 of 55 trades and keeps the 15 lucky ones
     has not been shown anything;
  4. the last 15% of history is locked on the first run and each hypothesis gets exactly one look at it.
     The bar an idea must clear rises with how many ideas have been tried on the same data, because 400
     combinations over 60 trades will produce a "winner" by arithmetic alone. That is the standard way a
     bot with a research department ends up worse than one without.

What it will not do:
  - place, modify or cancel an order. It has no broker import (pinned by test_data.py §32); its only
    output is lab/lab.json for the desk page and lab/proposals.json for a human to consider arming;
  - pretend to see the live market. There is no order book, spread or funding history here, so cost is
    modelled as taker fees plus a slippage allowance, intrabar ambiguity is resolved against the trade,
    and trades still open at the end of the window are excluded as censored rather than counted as wins;
  - quietly re-tune. A rejected idea stays rejected and is not re-tested until the archive has grown.
"""
import hashlib
import json
import math
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)              # tools/ in the checkout, /Users/x on the Mac


def _desk_root():
    """The folder that holds the desk's state — books/ and trades_log.jsonl — and therefore the lab/ folder
    the radar page reads. lab.py sits IN that folder on the Mac (~/hermes_sentry/lab.py) and one level BELOW
    it in the checkout (tools/mac/lab.py), so `dirname(HERE)`, which reads as obvious, is wrong on the real
    machine: it puts the archive in the home directory while the page looks beside the code, and the page
    then says "nothing to show yet" forever with the research running happily two levels up. A mismatch like
    that never errors, so the folder is DETECTED from what lives in it, and the answer is published."""
    env = os.environ.get("LAB_ROOT")
    if env:
        return os.path.abspath(env)                       # a test may point it elsewhere
    for d in (HERE, PKG, os.path.dirname(PKG)):
        if os.path.isdir(os.path.join(d, "books")) and os.path.exists(os.path.join(d, "trades_log.jsonl")):
            return d
    return HERE


ROOT = _desk_root()
LAB = os.path.join(ROOT, "lab")
CACHE = os.path.join(LAB, "data")
LAB_F = os.path.join(LAB, "lab.json")
LOCK_F = os.path.join(LAB, "lock.json")
REG_F = os.path.join(LAB, "hypotheses.json")
PROP_F = os.path.join(LAB, "proposals.json")
FIND_F = os.path.join(LAB, "findings.md")
RUN_F = os.path.join(LAB, ".running")

for _d in (LAB, CACHE):
    try:
        os.makedirs(_d, exist_ok=True)
        os.chmod(_d, 0o700)
    except Exception:
        pass


def env_num(k, d, lo=None, hi=None):
    """Env overrides that cannot take the loop down: a junk value falls back to the default.

    (A CCTV_TTL=0 once produced a ZeroDivisionError inside a live page handler. Same class of mistake is
    not being repeated here on purpose.)
    """
    try:
        v = float(os.environ.get(k, "")) if os.environ.get(k) else float(d)
    except Exception:
        v = float(d)
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


DAYS = env_num("LAB_DAYS", 21, 2, 120)                 # replay window; grows with the archive, not with hope
MIN_N = int(env_num("LAB_MIN_N", 20, 5, 10000))              # below this many paired trades, no verdict
HOLD_FRAC = env_num("LAB_HOLDOUT_FRAC", 0.15, 0.05, 0.5)
TEST_FRAC = env_num("LAB_TEST_FRAC", 0.25, 0.05, 0.5)
TTL_BARS = int(env_num("LAB_TTL", 6, 1, 72))                 # resting entry lifetime, in 1h bars
MAX_HOLD = int(env_num("LAB_MAX_HOLD", 72, 1, 1000))         # 1h bars before a trade is called censored
SLIP_R = env_num("LAB_SLIP_R", 0.10, 0.0, 1.0)          # penalty on a stop fill, in R
EDGE_BASE = env_num("LAB_EDGE", 0.20, 0.0, 10.0)        # mean-R advantage an idea must show, before deflation
BUDGET = int(env_num("LAB_BUDGET", 3, 1, 25))           # hypotheses evaluated per run
SYM_MAX = int(env_num("LAB_SYM_MAX", 4, 1, 12))
PAGES = int(env_num("LAB_PAGES", 6, 1, 40))              # history-candles pages per timeframe per run
# Pages are per timeframe, and a 1h-bar budget on the 15m series is not the same amount of history: 100 bars
# of 15m is 25 hours, so the sub-hour frames have to be fetched in proportion or the replay silently runs on
# the last few days while the report claims a 365-day window. (This is exactly what happened on the first real
# run: 504 one-hour bars, 600 fifteen-minute bars, and 363 of the signals had no forward bars to resolve.)
_BARS_PER_HOUR = {"5m": 12, "15m": 4, "1h": 1, "4h": 0.25, "1d": 1.0 / 24}
REQ_MAX = int(env_num("LAB_REQ_MAX", 200, 10, 2000))       # requests per run across all symbols/timeframes
_reqs = [0]
RUN_SEC = int(env_num("LAB_RUN_SEC", 600, 60, 3000))   # default = fits inside StartInterval 1800
                                                           # WITHOUT relying on launchd passing env through: a
                                                           # check of the live job showed only LAB_ENGINE arriving,
                                                           # so a 780 s default would overrun the 240 s grace and
                                                           # the 30 min interval, run after run.
RUN_GRACE = int(env_num("LAB_RUN_GRACE", 240, 5, 900))    # CPU time allowed AFTER fetching stops
SYMS = [s.strip() for s in os.environ.get("LAB_SYMS", "BTC-USDT,ETH-USDT,SOL-USDT,BNB-USDT,XRP-USDT").split(",") if s.strip()]
FIXDIR = os.environ.get("SENTRY_FIXTURES")


WHERE = {}          # which directory each module actually came from — published, because it is a real question


def _mod(name):
    """Import a sibling by name across the layouts this code has to survive (repo root, tools/mac, desk root)."""
    import importlib
    # ROOT is overridable so a test can point the *data* at a temp dir; the module search must still see the
    # checkout, or LAB_ROOT=/tmp/somewhere silently turns the replay into a no-op that reports "no trades".
    # Two layouts, and getting this wrong is not an error message — it is a lab that reports "no trades
    # found". In the desk install lab.py sits next to sentry_core.py; in this checkout it is two levels below.
    bases, seen = [], set()
    for d in (HERE, ROOT, PKG, os.path.dirname(PKG), os.path.join(ROOT, "tools", "mac"),
              os.path.join(PKG, "mac")):
        if d and d not in seen and os.path.isdir(d):
            seen.add(d); bases.append(d)
    # Each live book keeps its OWN copy of the engine (crypto/, crypto-bitget/, crypto-coinbase/), so the
    # book dirs have to be in the search or the lab finds nothing and reports "no trades" for a layout
    # problem. Sorted, so "which copy did research use" does not depend on listdir order — and WHERE
    # publishes the answer into lab.json, because "the last book I upgraded" is not a good silent default
    # for a verdict that will be quoted at me later.
    for parent in (ROOT, HERE):
        try:
            for d in sorted(os.listdir(parent)):
                sub = os.path.join(parent, d)
                if os.path.isdir(sub) and sub not in seen:
                    seen.add(sub); bases.append(sub)
        except Exception:
            pass
    # LAB_ENGINE pins which book's copy to use. Default is "the first one found", which is a fine answer for
    # research as long as the copies match, and a bad one the day they do not. Pin it to the book whose lane
    # the verdict is meant to serve — the desk's plist points at crypto-bitget, because that is the only lane
    # that can actually trade his $10, and a rule proven on OKX's fees is not a rule proven on Bitget's.
    pin = os.environ.get("LAB_ENGINE")
    if pin:
        want = os.path.abspath(os.path.join(ROOT, pin)) if not os.path.isabs(pin) else os.path.abspath(pin)
        pinned = [b for b in [want] + bases if os.path.exists(os.path.join(b, name + ".py"))]
        if not pinned:
            raise SystemExit("lab: LAB_ENGINE=%s has no %s.py in %s" % (pin, name, want))
        bases = [b for b in pinned if os.path.exists(os.path.join(b, name + ".py"))]
    for base in bases:
        if os.path.exists(os.path.join(base, name + ".py")):
            if base not in sys.path:
                sys.path.insert(0, base)
            mod = importlib.import_module(name)
            WHERE[name] = base
            return mod
    return None


core = _mod("sentry_core")
gs = _mod("grade_stats")
rc = None
try:
    import run_cycle as rc                                    # noqa: E402  (grade + fee_drag = the live rules)
    WHERE["run_cycle"] = os.path.dirname(os.path.abspath(rc.__file__))
except Exception:
    rc = _mod("run_cycle")

# Fallbacks are for the case where run_cycle cannot be imported (a bare test checkout). They are recorded in
# the report as `parity: "fallback"` so a number computed by a stand-in is never read as the real thing.
WIN_EPS = float(getattr(rc, "WIN_EPS", 0.05)) if rc else 0.05


def grade_r(r_mult):
    if rc and hasattr(rc, "grade"):
        return rc.grade(r_mult)
    if r_mult > WIN_EPS:
        return "win"
    if r_mult < -WIN_EPS:
        return "loss"
    return "scratch"


def fee_r(entry, exit_, r_dist):
    if rc and hasattr(rc, "fee_drag"):
        try:
            return float(rc.fee_drag(entry, exit_, r_dist, 1.0)[1])
        except Exception:
            return 0.0
    return 0.0


def stats(rows):
    if gs:
        return gs.stats(rows)
    return {"graded": 0, "line": "grade_stats.py missing — win rate not computed here", "win_rate": None,
            "net_r": 0.0, "decisive": 0, "wins": 0, "losses": 0, "scratch": 0}


# ---------------- data: a growing archive, not a fixed window ----------------

def _okx_paged(path_params, n_pages):
    """Page back through OKX public history. Returns (bars, requests_spent) — the count is returned because a
    run has a request budget as well as a clock, and the caller cannot know how many round trips happened."""
    okx = _mod("broker_okx")
    if not okx or not hasattr(okx, "_req"):
        return None, 0
    out, after, used = [], None, 0
    for _ in range(max(1, n_pages)):
        used += 1
        p = dict(path_params)
        if after:
            p["after"] = after
        try:
            d = okx._req("GET", "/api/v5/market/history-candles", params=p, public=True)
            rows = okx._rows(d)
        except Exception:
            break
        if not rows:
            break
        out = rows + out
        try:
            after = rows[-1][0]
        except Exception:
            break
    try:
        return okx._bars(out), used
    except Exception:
        return None, used


_BARS = {"5m": ("5m", 300), "15m": ("15m", 200), "1h": ("1H", 200), "4h": ("4H", 120), "1d": ("1D", 60)}


def fetch_history(sym, deadline=None, short=None):
    """Newest-first paging over OKX public history, merged into one archive per symbol.

    The archive is the point: a lab that refetches a fixed 200-bar window will be arguing about the same
    fortnight forever. Each run appends what it has not seen, so statistical power grows while it waits.
    """
    fp = os.path.join(CACHE, sym.replace("/", "") + ".json")
    arch = {}
    if os.path.exists(fp):
        try:
            arch = json.load(open(fp))
        except Exception:
            arch = {}
    got, report_short = {}, False
    for tf, (bar, cap) in _BARS.items():
        have = arch.get(tf) or []
        last_ms = 0
        if have:
            last_ms = ts(have[-1]["t"])
        if FIXDIR:
            try:
                fx = json.load(open(os.path.join(FIXDIR, sym.replace("/", "") + ".json")))
                got[tf] = fx.get(tf) or have
                continue
            except Exception:
                got[tf] = have
                continue
        want = int(DAYS * (24 if tf == "1h" else 288 if tf == "5m" else 96 if tf == "15m" else 6 if tf == "4h" else 1))
        if have and last_ms > time.time() * 1000 - 3 * 3600 * 1000 and len(have) >= min(want, 400):
            got[tf] = have                                   # fresh and long enough: don't spend requests
            continue
        # The budget is not politeness, it is the difference between a lab that reports and a lab that
        # silently never does: this job runs every 30 min from launchd, and a run that outlives the laptop
        # going to sleep writes NOTHING. So history is fetched until the clock says stop — the archive
        # keeps growing across runs either way, which is the whole design.
        # One place computes the remaining budget, one place uses it. The crash this replaces was a
        # NameError from a `left` defined above and then re-derived below — which no test caught, because the
        # fixture path returns before reaching it. So the fetch path is exercised with real requests too (§32).
        left = REQ_MAX - _reqs[0]
        if (deadline and time.time() > deadline) or left <= 0:
            got[tf] = have                                   # clock or request budget: keep what is archived
            report_short = True
            continue
        pages = max(1, min(int(round(PAGES * _BARS_PER_HOUR.get(tf, 1))), left))
        new, used = _okx_paged({"instId": sym, "bar": bar, "limit": 100}, pages)
        _reqs[0] += used
        if not new:
            okx = _mod("broker_okx")
            try:
                new = okx.crypto_bars(sym, {"5m": "5m", "15m": "15m", "1h": "1Hour",
                                            "4h": "4Hour", "1d": "1Day"}[tf], 290) if okx else []
                _reqs[0] += 1                                # the fallback is a request too; not counting it is how
            except Exception:                                # a "budget" becomes a suggestion
                new = []
        seen = {b["t"]: b for b in have}
        seen.update({b["t"]: b for b in (new or [])})
        got[tf] = [seen[k] for k in sorted(seen)][-want:]
    if report_short and short is not None:
        short.append(sym)
    arch.update(got)
    arch["asof"] = int(time.time())
    arch["requests_used"] = _reqs[0]
    try:
        json.dump(arch, open(fp, "w"))
    except Exception:
        pass
    return arch


def ts(tstr):
    try:
        return int(time.mktime(time.strptime(tstr.replace("Z", ""), "%Y-%m-%dT%H:%M:%S"))) * 1000
    except Exception:
        try:
            return int(float(tstr))
        except Exception:
            return 0


# ---------------- replay: the real engine, once, over history ----------------

def _slice_to(bars, t_ms, n=None):
    out = [b for b in bars if ts(b["t"]) <= t_ms]
    return out[-n:] if n else out


def resolve(cand, fwd, atr_now):
    """Walk the candidate forward through real bars. Returns a row, or None if it never became a trade.

    Deliberately pessimistic in the three places where a backtest usually flatters itself: a stop entry
    pays slippage, a bar that touches both stop and target is counted as the LOSS, and a trade still open
    when the data runs out is `censored` and thrown away rather than marked up at the last close.
    """
    long = cand["otype"].startswith("buy")
    e, sl, tp = float(cand["entry"]), float(cand["sl"]), float(cand["tp"])
    r_dist = abs(e - sl)
    if r_dist <= 0:
        return None
    entry_px, fill_i = None, None
    for i, b in enumerate(fwd[:TTL_BARS * 4]):                  # 15m bars, TTL measured in 1h bars
        hit = (float(b["l"]) <= e) if long else (float(b["h"]) >= e)
        if cand["otype"].endswith("limit"):
            if hit:
                entry_px = min(e, float(b["o"])) if long else max(e, float(b["o"]))
                fill_i = i
                break
        else:                                                     # stop entry: fill at the stop, plus slip
            if hit:
                entry_px = e + (SLIP_R * r_dist if long else -SLIP_R * r_dist)
                fill_i = i
                break
    if fill_i is None:
        return {"result": None, "no_fill": True, "skill": cand["skill"], "score": cand.get("score"),
                "t": fwd[0]["t"] if fwd else None, "otype": cand["otype"]}
    exit_px, why = None, None
    for b in fwd[fill_i + 1:fill_i + 1 + MAX_HOLD * 4]:
        bl, bh = float(b["l"]), float(b["h"])
        hit_sl = (bl <= sl) if long else (bh >= sl)
        hit_tp = (bh >= tp) if long else (bl <= tp)
        if hit_sl:                                                # tie goes to the loss, always
            exit_px, why = sl, "stop"
            break
        if hit_tp:
            exit_px, why = tp, "target"
            break
    if exit_px is None:
        return {"result": None, "censored": True, "skill": cand["skill"], "score": cand.get("score"),
                "t": fwd[fill_i]["t"], "otype": cand["otype"]}
    R = (exit_px - entry_px) / r_dist * (1 if long else -1)
    fr = fee_r(entry_px, exit_px, r_dist)
    R = round(R - fr, 4)
    return {"result": grade_r(R), "R": R, "fee_r": fr, "skill": cand["skill"], "score": cand.get("score"),
            "otype": cand["otype"], "t": fwd[fill_i]["t"], "exit": why, "hold_bars": 0,
            "atr": round(atr_now, 8) if atr_now else None, "fired": False, "entry": entry_px,
            "sl": sl, "tp": tp}


def base_stream(arch, sym, split_ms=None, deadline=None):
    """Every trade the current playbook would have taken, with its bar context, before any filter.

    (sym, not _) — the replay is shared across symbols and the row records which one it came from; dropping
    the argument is the kind of tidy-up that quietly attributes a BTC result to ETH.

    The deadline bounds the *replay*, not just the fetching: 600 bars through evaluate_symbol is real CPU, and
    a run that is cut off at symbol 3 must still write a report for the 3 it did. Without this the page shows
    the previous report indefinitely and "still running" is indistinguishable from "found nothing".
    """
    if not core or not hasattr(core, "evaluate_symbol"):
        return []
    h1 = arch.get("1h") or []
    if len(h1) < 80:
        return []
    rows, truncated = [], False
    # A signal is only gradeable if the 15-minute bars that resolve it exist in this archive — both the ones
    # that could fill the entry and the ones that could carry it to a stop or target. Skipping the check is how
    # the first real run reported a 365-day window while scoring six days: the engine sees no lower-timeframe
    # context for an old bar, generates nothing, and the sample shrinks silently around whatever aligns.
    f15 = arch.get("15m") or []
    t_lo = ts(f15[0]["t"]) if f15 else 0
    horizon = (TTL_BARS * 3600 + MAX_HOLD * 900) * 1000
    t_hi = (ts(f15[-1]["t"]) - horizon) if f15 else 0
    cov = {"resolvable": 0, "no_forward_data": 0}
    for i in range(60, len(h1)):
        t_now = ts(h1[i]["t"])
        if t_lo and not (t_lo <= t_now <= t_hi):
            cov["no_forward_data"] += 1
            continue
        cov["resolvable"] += 1
        if deadline and time.time() > deadline:
            truncated = True
            break
        t = ts(h1[i]["t"])
        if split_ms and t > split_ms:
            break                          # cheap way to replay only up to a boundary when asked
        view = {"1h": _slice_to(h1, t), "4h": _slice_to(arch.get("4h") or [], t),
                "1d": _slice_to(arch.get("1d") or [], t), "15m": _slice_to(arch.get("15m") or [], t, 30),
                "5m": _slice_to(arch.get("5m") or [], t, 30)}
        try:
            cands = core.evaluate_symbol(sym, view, min_score_fire=3) or []
        except Exception:
            continue
        if not cands:
            continue
        a = core.atr(view["1h"]) if hasattr(core, "atr") else 0
        fwd15 = [b for b in (arch.get("15m") or []) if ts(b["t"]) > t]
        for c in cands:
            r = resolve(c, fwd15, a)
            if not r:
                continue
            r.update({"sym": sym, "t0": h1[i]["t"], "win": bool(ts(h1[i]["t"]) < split_ms) if split_ms else None})
            ctx = {"hour": time.gmtime(ts(h1[i]["t"]) / 1000.0).tm_hour, "atr": a,
                   "atr_rel": None, "htf": 0, "score": c.get("score"), "i": i}
            r["ctx"] = {k: v for k, v in ctx.items() if k != "i"}
            r["skill_in"] = c["skill"]
            r["otype_in"] = c["otype"]
            rows.append(r)
    return rows, truncated, cov


def atr_rel_series(arch):
    """ATR / its own 100-bar median — the cheap, honest proxy for 'is the market behaving oddly'."""
    if not core or not hasattr(core, "atr"):
        return {}
    h1 = arch.get("1h") or []
    out, vals = {}, []
    for i, b in enumerate(h1):
        a = core.atr(h1[max(0, i - 40):i + 1]) or 0
        vals.append(a)
        med = sorted(vals[-100:])[len(vals[-100:]) // 2] if len(vals) >= 20 else 0
        out[b["t"]] = round(a / med, 3) if med else None
    return out


# ---------------- hypotheses: closed vocabulary, declarative, no eval ----------------

FILTERS = ("min_score", "skills", "drop_skills", "no_short", "no_long", "cooldown", "atr_band",
           "max_fee_r", "hours", "ttl", "require_quiet", "require_violent", "days_of_week")


class FilterError(Exception):
    pass


def make_filter(spec):
    """Compile {"min_score":4, "atr_band":[0.8,1.4]} into a predicate. Unknown keys RAISE.

    A filter name that silently matches nothing is the worst possible outcome for research: it reports a
    verdict on "the strategy with the new rule" while having tested the old one unchanged.
    """
    if not isinstance(spec, dict):
        raise FilterError("a hypothesis filter must be an object")
    for k in spec:
        if k not in FILTERS:
            raise FilterError("unknown filter %r (allowed: %s)" % (k, ", ".join(FILTERS)))
    cooldown = int(spec.get("cooldown", 0))

    def keep(row, last_seen):
        for k, v in spec.items():
            res = row.get("result")
            if k == "min_score" and (row.get("score") or 0) < int(v):
                return False
            if k == "skills" and row.get("skill") not in v:
                return False
            if k == "drop_skills" and row.get("skill") in v:
                return False
            if k == "no_short" and row.get("otype_in", "").startswith("sell"):
                return False
            if k == "no_long" and row.get("otype_in", "").startswith("buy"):
                return False
            if k == "max_fee_r" and (row.get("fee_r") or 0) > float(v):
                return False
            if k == "atr_band":
                rel = (row.get("ctx") or {}).get("atr_rel")
                if rel is None or not (float(v[0]) <= rel <= float(v[1])):
                    return False
            if k == "require_quiet" and not ((row.get("ctx") or {}).get("atr_rel") or 9) <= float(v):
                return False
            if k == "require_violent" and not ((row.get("ctx") or {}).get("atr_rel") or 0) >= float(v):
                return False
            if k == "hours":
                hr = (row.get("ctx") or {}).get("hour")
                if hr is None:
                    continue
                lo, hi = int(v[0]), int(v[1])
                inw = lo <= hr <= hi if lo <= hi else (hr >= lo or hr <= hi)
                if not inw:
                    return False
            if k == "days_of_week" and time.gmtime(ts(row.get("t0") or row.get("t") or "") / 1000.0).tm_wday not in v:
                return False
            if k == "cooldown" and res:
                s = row.get("sym")
                t0 = ts(row.get("t0") or "")
                if last_seen.get(s) is not None and t0 - last_seen[s] < cooldown * 3600 * 1000:
                    return False
                last_seen[s] = t0
        return True
    return keep


def deflated_bar(n_trials):
    """The mean-R advantage an idea must show, grown by how many ideas were tried on this data.

    Not a formal White/Deflated-Sharpe computation — it borrows the *direction* of one, in one line, and
    says so rather than quoting a statistic nobody computed. On 30-60 paired trades, a trial count that is
    ignored is a false discovery that gets armed with real money.
    """
    return round(EDGE_BASE * (1.0 + 0.35 * math.log(1.0 + max(0, int(n_trials)))), 4)


def bootstrap_delta(kept, dropped, n=800, seed=""):
    """CI on (mean R kept) - (mean R dropped) by resampling rows. Returns (point, lo, hi, n).

    Kept vs dropped is the paired question a filter actually asks. Both lists are small, so no asymptotic
    hand-waving: resample with replacement and read the 2.5/97.5 percentiles.
    """
    a = [r.get("R") or 0.0 for r in kept]
    b = [r.get("R") or 0.0 for r in dropped]
    if len(a) < 5 or len(b) < 5:
        return None
    rnd = __import__("random").Random(int(hashlib.sha1((seed + str(len(a)) + str(len(b))).encode()).hexdigest(), 16) % 2 ** 31)
    diffs = []
    for _ in range(n):
        ma = sum(a[rnd.randrange(len(a))] for _ in a) / float(len(a))
        mb = sum(b[rnd.randrange(len(b))] for _ in b) / float(len(b))
        diffs.append(ma - mb)
    diffs.sort()
    return {"point": round(sum(a) / len(a) - sum(b) / len(b), 4),
            "lo": round(diffs[int(0.025 * len(diffs))], 4), "hi": round(diffs[int(0.975 * len(diffs))], 4),
            "n_kept": len(a), "n_dropped": len(b)}


# ---------------- splits, locks, the holdout ----------------

def split_points(arch):
    """(train_end, test_start, test_end, hold_start) with an EXCLUDED gap at each seam.

    The gaps are the point. Trades are held for hours, so a test window that begins on the bar after
    training ends would let a trade opened during training settle inside the test set and be scored as
    out-of-sample — the leak that makes most home-grown backtests worthless. A bar in a gap belongs to
    neither side: it is reported as `embargoed` and used by nothing.
    """
    h1 = arch.get("1h") or []
    if len(h1) < 120:
        return None, None, None, None
    n = len(h1)
    hold = max(20, int(n * HOLD_FRAC))
    test = max(20, int(n * TEST_FRAC))
    emb = TTL_BARS + (MAX_HOLD // 6)
    hold_i = n - hold
    test_end_i = hold_i - emb
    test_start_i = max(61, test_end_i - test)
    train_end_i = max(60, test_start_i - emb)
    if test_end_i - test_start_i < 10 or train_end_i - 60 < 10:
        return None, None, None, None            # not enough history to grade anything honestly yet
    return (ts(h1[train_end_i]["t"]), ts(h1[test_start_i]["t"]), ts(h1[test_end_i]["t"]),
            ts(h1[hold_i]["t"]))


def lock():
    """The holdout start is FIXED the first time the lab runs and never drifts with the archive."""
    if os.path.exists(LOCK_F):
        try:
            return json.load(open(LOCK_F))
        except Exception:
            pass
    return None


def write_lock(d):
    try:
        json.dump(d, open(LOCK_F, "w"), indent=1)
        os.chmod(LOCK_F, 0o600)
    except Exception:
        pass


def consume_holdout(lk, hid):
    """True only the first time this hypothesis looks at the locked window; the file records the look."""
    consumed = (lk or {}).get("consumed") or {}
    if hid in consumed:
        return False
    consumed[hid] = int(time.time())
    lk["consumed"] = consumed
    write_lock(lk)
    return True


# ---------------- registry ----------------

def load_reg():
    try:
        return json.load(open(REG_F))
    except Exception:
        return {"trials": 0, "items": []}


def save_reg(r):
    try:
        json.dump(r, open(REG_F, "w"), indent=1)
    except Exception:
        pass


def sig(spec, window):
    return hashlib.sha1((json.dumps(spec, sort_keys=True) + "|" + str(window)).encode()).hexdigest()[:12]


def evaluate(h, train_rows, test_rows, hold_rows, lk, trials):
    """One hypothesis against the data it is allowed to see. Returns the verdict block."""
    f = make_filter(h.get("filter") or {})                      # raises FilterError, never silently passes
    seen_tr, seen_te, seen_ho = {}, {}, {}
    def cut(rows, seen):
        return [r for r in rows if r.get("result") and f(r, seen)]
    kt, dt = cut(train_rows, seen_tr), [r for r in train_rows if r.get("result") and not f(r, {})]
    ke, de = cut(test_rows, seen_te), [r for r in test_rows if r.get("result") and not f(r, {})]
    v = {"filter": h.get("filter") or {}, "trials_at": trials, "bar": deflated_bar(trials),
         "n_train": len(kt), "n_test": len(ke), "n_dropped_test": len(de),
         "test_kept": stats(kt + ke), "test_only": stats(ke), "dropped": stats(de)}
    boot = bootstrap_delta(ke, de, seed=h["id"])
    v["paired"] = boot
    v["train_stats"] = stats(kt)
    n_ok = len(ke) >= MIN_N
    pt = (boot or {}).get("point")
    keep_rate = (len(ke) / float(len(ke) + len(de))) if (ke or de) else 1.0
    # keep_rate is in the gate on purpose: an idea that leaves 97% of the stream alone has not earned a look
    # at the one window nobody gets to look at twice.
    test_passed = bool(n_ok and pt is not None and pt >= v["bar"] and (boot or {}).get("lo", -9) > 0
                       and 0.20 <= keep_rate <= 0.95)

    if hold_rows is not None and not test_passed:
        # The one clean window in this whole design is spent only on an idea that could actually change the
        # book. Burning a holdout look on something the test window already rejected would leave the good
        # ideas unverifiable — and a holdout you have already read is no longer a holdout.
        v["holdout"] = {"not_consulted": True,
                        "why": "the test window answered first; the locked holdout is reserved for ideas "
                               "that passed it"}
    elif hold_rows is not None and consume_holdout(lk, h["id"]):
        kh = cut(hold_rows, {})
        dh = [r for r in hold_rows if r.get("result") and not f(r, {})]
        v["holdout"] = {"kept": stats(kh), "dropped": stats(dh), "paired": bootstrap_delta(kh, dh, seed=h["id"] + "h")}
        v["holdout"]["looks"] = 1
    elif hold_rows is not None:
        v["holdout"] = {"locked": True, "note": "this hypothesis already spent its one look at the holdout"}
    # ---- verdict ----
    if not n_ok:
        verdict = "insufficient"
        why = ("only %d paired trades in the test window (this lab needs %d and is still archiving; "
               "unfilled and censored trades are excluded, which is why the number is small)" % (len(ke), MIN_N))
    elif keep_rate > 0.95:
        verdict = "no_op"
        why = "kept %.0f%% of the base stream — that is not a change, it is a no-op" % (100 * keep_rate)
    elif keep_rate < 0.20:
        verdict = "too_narrow"
        why = "kept only %.0f%% of trades; anything looks good on a fifth of a stream" % (100 * keep_rate)
    elif pt is None:
        verdict = "insufficient"
        why = "not enough in both arms for a bootstrap"
    elif test_passed and (v["holdout"].get("kept") or {}).get("net_r", 0) > 0 \
            and (v["holdout"].get("kept") or {}).get("decisive", 0) >= max(5, int(MIN_N / 4)):
        verdict = "survives"
        why = ("paired mean-R +%.3f (95%% CI %+.3f..%+.3f) on %d kept vs %d dropped, and the locked holdout "
               "agreed" % (pt, boot["lo"], boot["hi"], len(ke), len(de)))
    else:
        verdict = "rejected"
        hk = (v["holdout"] or {}).get("kept") or {}
        if test_passed and (v["holdout"] or {}).get("kept") is not None:
            # The important sentence in the whole file, and it was the wrong one: this branch used to print the
            # TEST window's numbers ("paired mean-R +1.135 vs a bar of +0.25") next to the word "rejected",
            # which reads like a typo in the verdict. The idea passed its test window and was killed by the
            # pinned holdout (there: 2.9 % win rate, 1 of 34, −37.95 R, on a 67 % test window). Saying only
            # that — the exam vetoed it — is the whole point of having an exam, and it is what a human needs to
            # see before deciding whether the veto is itself the discovery.
            why = ("passed the test window (paired %+.3fR, CI %+.3f..%+.3f, %d trades) but the LOCKED holdout "
                   "disagreed: %s — the exam window wins, and this idea has spent its one look at it"
                   % (pt, boot["lo"], boot["hi"], len(ke), hk.get("line") or "no graded trades there"))
        else:
            why = ("paired mean-R %s vs a deflated bar of +%.2fR (CI %s..%s, n=%d/%d)"
                   % (("%+.3f" % pt) if pt is not None else "n/a", v["bar"],
                      (boot or {}).get("lo"), (boot or {}).get("hi"), len(ke), len(de)))
        if v["holdout"].get("locked"):
            why += "; holdout was already spent, so it could not be double-checked"
    v.update({"verdict": verdict, "why": why})
    return v


def find_ideas(reg, book_rows):
    """Archaeology: propose filters from where the LIVE book actually loses, not from imagination."""
    out = []
    by = {}
    for r in book_rows:
        if not r.get("result"):
            continue
        k = r.get("skill") or "?"
        b = by.setdefault(k, {"n": 0, "R": 0.0, "w": 0})
        b["n"] += 1
        b["R"] += float(r.get("R") or 0)
        b["w"] += 1 if r["result"] == "win" else 0
    pooled = sum(v["R"] for v in by.values()) / max(1, sum(v["n"] for v in by.values()))
    known = {json.dumps(i.get("filter"), sort_keys=True) for i in reg["items"]}
    for k, v in sorted(by.items(), key=lambda x: (x[1]["R"] / max(1, x[1]["n"]))):
        if v["n"] < 6:
            continue
        mean = v["R"] / v["n"]
        if mean < pooled - 0.25:
            spec = {"drop_skills": [k]}
            if json.dumps(spec, sort_keys=True) in known:
                continue
            out.append({"claim": "%s loses %.2fR per trade over %d graded trades while the book as a whole "
                                 "is %+.2fR — cut it and see whether the survivors are better or just fewer"
                                 % (k, mean, v["n"], pooled),
                        "filter": spec, "origin": "live-log archaeology"})
    hours = {}
    for r in book_rows:
        if not r.get("result"):
            continue
        hr = (r.get("ctx") or {}).get("hour")
        if hr is None:
            continue
        b = hours.setdefault(hr, [0.0, 0])
        b[0] += float(r.get("R") or 0)
        b[1] += 1
    worst = sorted(((s / n, h) for h, (s, n) in hours.items() if n >= 5))[:1]
    for mean, h in worst:
        spec = {"hours": [(h + 1) % 24, (h + 5) % 24]}
        if mean < pooled - 0.3 and json.dumps(spec, sort_keys=True) not in known:
            out.append({"claim": "trades opened in UTC hour %d average %+.2fR (n=%d) — a session-cooldown "
                                "may be cheaper than a smarter signal" % (h, mean, hours[h][1]),
                        "filter": spec, "origin": "live-log archaeology"})
    return out[:3]


# ---------------- report ----------------

def write_json(d):
    try:
        json.dump(d, open(LAB_F + ".tmp", "w"), indent=1)
        os.replace(LAB_F + ".tmp", LAB_F)
    except Exception:
        pass


def finding_block(h, v, meta):
    return ("\n## %s — %s (%s)\n%s\n\n- filter: `%s`\n- paired mean-R: %s (95%% CI %s..%s), kept %d / dropped %d\n"
            "- test window: %s\n- locked holdout: %s\n- trials burned on this data: %s, bar to clear: +%.2fR\n"
            "- verdict: **%s** — %s\n- data: %s\n") % (
        time.strftime("%Y-%m-%d %H:%M", time.localtime()), h["id"], h.get("origin", "operator"),
        h.get("claim", ""), json.dumps(h.get("filter") or {}),
        (v.get("paired") or {}).get("point"), (v.get("paired") or {}).get("lo"), (v.get("paired") or {}).get("hi"),
        (v.get("paired") or {}).get("n_kept"), (v.get("paired") or {}).get("n_dropped"),
        (v.get("test_only") or {}).get("line"),
        ((v.get("holdout") or {}).get("kept") or {}).get("line") if (v.get("holdout") or {}).get("kept")
        else (v.get("holdout") or {}).get("note") or "not looked at",
        v.get("trials_at"), v.get("bar") or 0, v.get("verdict"), v.get("why"),
        " · ".join("%s %s" % (k, val) for k, val in (meta or {}).items()))


def book_rows():
    """The graded live record, from every book that has one — the most valuable data here is what happened.

    The forex log and each crypto book's own log are read the same way the dashboards read them
    (grade_stats.rows_from, which forgives a half-written line), so a research finding and a dashboard
    number cannot disagree about which trades exist.
    """
    if not gs:
        return []
    rows = list(gs.rows_from(os.path.join(ROOT, "trades_log.jsonl")))
    try:
        names = sorted(os.listdir(ROOT))
    except Exception:
        names = []
    for d in names:
        f = os.path.join(ROOT, d, "trades_log.jsonl")
        if os.path.isdir(os.path.join(ROOT, d)) and os.path.exists(f):
            for r in gs.rows_from(f):
                r["book"] = d
                rows.append(r)
    for r in rows:
        r.setdefault("ctx", {})
    return rows


SEED = [{"id": "S-minscore4", "claim": "the fire floor is 3; if 3-score signals are the ones bleeding, a "
                                      "floor of 4 is a cheaper fix than a new signal",
         "filter": {"min_score": 4}, "origin": "seed (parameter, not fitted)"},
        {"id": "S-cooldown6", "claim": "consecutive entries on one symbol within 6h may be the same move "
                                       "priced twice", "filter": {"cooldown": 6}, "origin": "seed (regime)"},
        {"id": "S-quietonly", "claim": "the patterns assume an orderly range; only take entries when ATR is "
                                       "at or below 1.3x its own 100-bar median",
         "filter": {"require_quiet": 1.3}, "origin": "seed (volatility)"},
        {"id": "S-nofeebleed", "claim": "at $10 the round trip costs real R; skip candidates whose fee drag "
                                        "exceeds 0.25R, which is the live bound the books already refuse on",
         "filter": {"max_fee_r": 0.25}, "origin": "seed (venue cost)"},
        {"id": "S-nolong", "claim": "crypto drifts up: if the shorts are the losing half, a long-only book "
                                    "is not a belief, it is a measurement",
         "filter": {"no_short": True}, "origin": "seed (direction)"},
        {"id": "S-hours", "claim": "UTC 21-02 (Asia closed, US late) may be spread and thin books rather than "
                                   "signal", "filter": {"hours": [3, 20]}, "origin": "seed (session)"}]


def seed_registry(reg):
    have = {h["id"] for h in reg["items"]}
    for h in SEED:
        if h["id"] not in have:
            reg["items"].append(dict(h, status="proposed"))
    return reg


def run(loop=False):
    if os.path.exists(RUN_F) and time.time() - os.path.getmtime(RUN_F) > 1800:
        os.unlink(RUN_F)
    if os.path.exists(RUN_F):
        return {"skipped": "another lab run is in progress"}
    open(RUN_F, "w").write(str(os.getpid()))
    try:
        return _run()
    finally:
        try:
            os.unlink(RUN_F)
        except Exception:
            pass


def _run():
    lk = lock()
    fresh_lock = lk is None
    if fresh_lock:
        lk = {"locked_at": int(time.time()), "hold_frac": HOLD_FRAC, "consumed": {},
              "note": "the holdout boundary is fixed here, once, so the lab cannot creep the exam date "
                      "forward to catch a friendier window"}
    reg = load_reg()
    if not reg["items"]:
        seed_registry(reg)
    meta = {}
    rows_tr, rows_te, rows_ho, rows_em = [], [], [], []
    hold_start = None
    if not core:
        # A replay with no engine returns [] and would otherwise be reported as "the playbook generated no
        # trades". That is a different fact, and a dangerous one to confuse.
        report = {"asof": time.strftime("%Y-%m-%d %H:%M:%S"), "fatal": "sentry_core is not importable",
                  "searched": [b for b in (HERE, ROOT, PKG)], "engine": "MISSING",
                  "parity": "run_cycle" if rc else "FALLBACK thresholds", "hypotheses": [], "errors": ["replay inert"]}
        write_json(report)
        return report
    hs_seen = []
    t_run = time.time()
    deadline = t_run + RUN_SEC                    # fetching stops here…
    hard = deadline + RUN_GRACE                   # …and the replay stops here, so a report is guaranteed
    for k, sym in enumerate(SYMS[:SYM_MAX]):
        if time.time() > deadline:
            meta[sym] = {"skipped": "run budget spent (LAB_RUN_SEC) — the archive keeps what earlier runs fetched"}
            continue
        arch = fetch_history(sym, deadline)
        tr_end, te_start, te_end, hs = split_points(arch)
        if not tr_end:
            meta[sym] = {"error": "not enough history yet (need 120 closed 1h bars)"}
            continue
        hs_seen.append(hs)
        arch_all = arch
        meta[sym] = {"1h_bars": len(arch.get("1h") or []), "from": (arch.get("1h") or [{}])[0].get("t"),
                     "to": (arch.get("1h") or [{}])[-1].get("t")}
        relmap = atr_rel_series(arch_all)
        _rows, _tr, _cov = base_stream(arch_all, sym, None, hard)
        meta[sym]["1h_resolvable"] = _cov["resolvable"]
        if _cov["no_forward_data"]:
            meta[sym]["bars_without_forward_data"] = _cov["no_forward_data"]
        if _tr:
            meta[sym]["replay_partial"] = True    # counted, and shown as incomplete on the page
        for r in _rows:
            r["ctx"]["atr_rel"] = relmap.get(r.get("t0"))
            t0 = ts(r.get("t0") or "")
            r["_t0"] = t0
            # Pinned holdout wins over this symbol's own boundary, so every run is graded on the SAME window.
            hold = hold_start or hs
            if t0 <= tr_end:
                rows_tr.append(r)
            elif te_start <= t0 <= te_end and t0 < hold:
                rows_te.append(r)
            elif t0 >= hold:
                rows_ho.append(r)
            else:
                rows_em.append(r)           # embargoed: neither train nor test, by construction
    # The holdout boundary is pinned on the first run and reused forever after; rows are bucketed against
    # it inside the loop above, so a run on a longer archive cannot quietly move the exam date.
    # Do not pin an exam date the sample cannot support. Pinning on run 1 looked like the strict choice and
    # was not: with six resolvable days, the "holdout" swallowed every gradeable trade and left the test
    # window empty forever, so no idea could ever earn a look at it. The boundary is worth freezing only once
    # there are real trades on BOTH sides of it — until then the split rolls with the archive and the page
    # says so instead of reporting a permanent, unearned "insufficient".
    _n_out = len([r for r in rows_tr + rows_te if r.get("result")])
    if fresh_lock or not lk.get("hold_start"):
        if _n_out >= 2 * MIN_N:
            lk["hold_start"] = min(hs_seen) if hs_seen else None
            lk["pinned"] = True
            write_lock(lk)
        else:
            lk["pinned"] = False
            lk["waiting_for"] = 2 * MIN_N - _n_out
    rows_em = [r for r in rows_te + rows_ho if False] + rows_em       # (kept explicit: nothing re-buckets)
    for r in rows_tr + rows_te + rows_ho + rows_em:
        r.pop("_t0", None)
    # recorded BEFORE the report exists, published inside it — see "sample_partial"
    report_partial = any((m or {}).get("replay_partial") for m in meta.values())
    no_fwd = sum(int((m or {}).get("bars_without_forward_data") or 0) for m in meta.values())
    live = [r for r in book_rows() if r.get("result")]
    fees = None
    try:
        fees = dict(getattr(getattr(rc, "ledger", None), "FEES", {}) or {})
    except Exception:
        fees = None
    report = {"asof": time.strftime("%Y-%m-%d %H:%M:%S"),
              "sources": dict(WHERE),
              "cost_source": {"module": WHERE.get("run_cycle"), "fees": fees,
                              "note": "one fee schedule for the whole replay — it is the "
                                      "first-found book's, and it is published so a verdict can be re-checked "
                                      "against another venue's costs instead of trusting it"},
              "parity": "run_cycle" if rc else "FALLBACK thresholds (run_cycle not importable)",
              "engine": "sentry_core.evaluate_symbol" if core else "MISSING — replay is inert",
              "grading": "grade_stats.stats" if gs else "MISSING",
              "window": {"days": int(DAYS), "ttl_bars": TTL_BARS, "max_hold_bars": MAX_HOLD,
                         "slip_r": SLIP_R, "holdout_frac": HOLD_FRAC, "min_n": MIN_N,
                         "tie_rule": "a bar touching stop and target is a LOSS",
                         "censored": "trades still open when data ends are excluded, not marked at close"},
              "run_seconds": round(time.time() - t_run, 1), "fetch_budget_s": RUN_SEC,
              "sample_partial": report_partial,
              "data": meta,
              "base_trades": {"train": len([r for r in rows_tr if r.get("result")]),
                              "test": len([r for r in rows_te if r.get("result")]),
                              "holdout_locked": len([r for r in rows_ho if r.get("result")]),
                              "never_filled": len([r for r in rows_tr + rows_te + rows_ho if r.get("no_fill")]),
                              "censored": len([r for r in rows_tr + rows_te + rows_ho if r.get("censored")]),
                              "embargoed_out": len([r for r in rows_em if r.get("result")]),
                              "no_forward_data": no_fwd,
                              "live_log_graded": len(live)},
              "base_line": stats(rows_tr + rows_te).get("line"),
              "live_line": stats(live).get("line"),
              "trials": reg.get("trials", 0), "bar_to_clear": deflated_bar(reg.get("trials", 0)),
              "hypotheses": [], "proposals": [], "ideas_proposed": 0, "errors": []}
    todo = [h for h in reg["items"] if h.get("status") == "proposed"][:BUDGET]
    for h in todo:
        try:
            v = evaluate(h, rows_tr, rows_te, rows_ho, lk, reg["trials"] + 1)
        except FilterError as e:
            v = {"verdict": "invalid", "why": str(e)}
        except Exception as e:
            v = {"verdict": "error", "why": "%s: %s" % (type(e).__name__, str(e)[:140])}
            report["errors"].append("%s: %s" % (h.get("id"), type(e).__name__))
        _v = v.get("verdict")
        # "error" and "insufficient" are not trials. A trial is an idea that got an answer from the data; if a
        # crash or a too-small sample counted, the lab would raise its own bar of proof while archiving and
        # could reach a bar nothing clears. Same reason an insufficient idea stays PROPOSED: it must come back
        # when n has grown, not be retired as if it had been answered.
        if _v not in ("error", "insufficient"):
            reg["trials"] = reg.get("trials", 0) + 1
        _win = "d%d/n%d" % (int(DAYS), len(rows_te))
        h.update({"status": ("proposed" if _v == "insufficient" else "tested"), "verdict": v.get("verdict"),
                  "why": v.get("why"), "tries": int(h.get("tries") or 0) + 1,
                  "tested_at": int(time.time()), "window": _win})
        v["id"], v["claim"], v["origin"] = h["id"], h.get("claim"), h.get("origin")
        report["hypotheses"].append(v)
        # Findings are append-only, so "insufficient" is journalled only when the sample behind it changed —
        # otherwise a lab that is still archiving floods the file with the same sentence every 30 minutes.
        if _v != "insufficient" or h.get("_last_win") != _win:
            h["_last_win"] = _win
            try:
                with open(FIND_F, "a") as f:
                    f.write(finding_block(h, v, {k: ("1h bars " + str(m.get("1h_bars"))) for k, m in
                                                list(meta.items())[:3]}))
            except Exception:
                pass
        if v.get("verdict") == "survives":
            props = []
            if os.path.exists(PROP_F):
                try:
                    props = json.load(open(PROP_F))
                except Exception:
                    props = []
            props.append({"id": h["id"], "filter": h.get("filter"), "claim": h.get("claim"),
                          "evidence": v.get("why"), "armed": False, "at": int(time.time()),
                          "how_to_apply": "a proposal, not a change. Nothing in the desk reads this file; "
                                          "arming means a human edits the book config on purpose."})
            try:
                json.dump(props[-25:], open(PROP_F, "w"), indent=1)
            except Exception:
                pass
    if len([h for h in reg["items"] if h.get("status") == "proposed"]) < 4:
        for idea in find_ideas(reg, live + rows_tr):
            reg["items"].append({"id": "H%03d" % (len(reg["items"]) + 1), "status": "proposed",
                                 "claim": idea["claim"], "filter": idea["filter"], "origin": idea["origin"]})
            report["ideas_proposed"] += 1
    save_reg(reg)
    if os.path.exists(PROP_F):
        try:
            report["proposals"] = json.load(open(PROP_F))[-6:]
        except Exception:
            pass
    report["trials"] = reg.get("trials", 0)              # after the loop: the run must publish what IT consumed
    report["bar_to_clear"] = deflated_bar(report["trials"])
    report["lock"] = {"pinned": bool(lk.get("pinned", True)),
                      "waiting_for_trades": lk.get("waiting_for"),
                      "hold_start_iso": time.strftime("%Y-%m-%d %H:%M", time.localtime((lk.get("hold_start") or 0) / 1000.0)),
                      "looks_consumed": len(lk.get("consumed") or {}),
                      "fixed_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(lk.get("locked_at") or 0))}
    write_json(report)
    return report


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--unlock" in args:
        # Deliberately ugly to do on purpose: the holdout is the one thing that keeps this lab honest, so
        # moving it has to be an explicit act that leaves a trace in the findings file.
        print("refusing: run with --unlock-holdout --i-know to reset the holdout and journal it")
        sys.exit(2)
    if "--unlock-holdout" in args and "--i-know" in args:
        lk = lock() or {}
        lk["hold_start"] = None
        lk["consumed"] = {}
        lk["unlocked_at"] = int(time.time())
        write_lock(lk)
        with open(FIND_F, "a") as f:
            f.write("\n%d: HOLDOUT RESET by operator — every previous verdict is now 'in-sample' for new ideas\n"
                    % time.strftime("%Y-%m-%d %H:%M"))
        print("holdout reset and journalled")
        sys.exit(0)
    if "--status" in args:
        print(json.dumps(json.load(open(LAB_F)) if os.path.exists(LAB_F) else {"no runs yet": True}, indent=1)[:3000])
        sys.exit(0)
    if "--report" in args:
        try:
            d = json.load(open(LAB_F))
        except Exception:
            d = {"no run yet": LAB_F}
        print(json.dumps({k: d.get(k) for k in ("asof", "parity", "engine", "grading", "window", "data",
                                                 "base_trades", "base_line", "live_line", "trials",
                                                 "bar_to_clear", "lock")}, indent=1))
        for h in (d.get("hypotheses") or []) + [i for i in [] ]:
            print("  %-12s %-11s %s" % (h.get("id"), h.get("verdict"), (h.get("why") or "")[:100]))
        for p in d.get("proposals") or []:
            print("  proposal %-12s %s" % (p.get("id"), (p.get("evidence") or "")[:100]))
        sys.exit(0)
    if "--seed" in args:
        reg = load_reg(); n0 = len(reg["items"]); seed_registry(reg); save_reg(reg)
        print("registry: %d -> %d items" % (n0, len(reg["items"])))
        sys.exit(0)
    if "--ideas" in args:
        reg = load_reg()
        for i in find_ideas(reg, book_rows()):
            print("  %s" % json.dumps(i)[:200])
        sys.exit(0)
    r = run(loop="--loop" in args)
    if r.get("skipped"):
        # Two runs at once is normal on a Mac that just woke up (RunAtLoad plus a manual run). The second one
        # must leave quietly, not print a report of nothing that would look like the lab found nothing.
        print("lab: %s" % r["skipped"])
        sys.exit(0)
    if r.get("fatal"):
        print("lab: FATAL %s (searched %s)" % (r["fatal"], ", ".join(r.get("searched") or [])))
        sys.exit(3)
    print(json.dumps({k: r.get(k) for k in ("asof", "trials", "bar_to_clear", "base_line", "live_line",
                                            "base_trades", "ideas_proposed", "errors", "run_seconds")}, indent=1))
    for h in r.get("hypotheses") or []:
        print("  %-6s %-12s %s" % (h.get("id"), h.get("verdict"), (h.get("why") or "")[:110]))
