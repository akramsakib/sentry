"""Sentry Core — the brain, ported from sentry_mac.py v3.1 (broker-agnostic, pure functions).

Same indicators, same playbook §12 candle engine, same scoring + accuracy-based self-sizing.
No I/O here: run_cycle.py feeds bars, consumes signals, broker.py executes.
"""
import json
import os

# ---------- indicators (verbatim logic from sentry_mac v3.1) ----------

def ema(vals, n):
    k = 2.0 / (n + 1)
    out = [sum(vals[:n]) / n]
    for v in vals[n:]:
        out.append(v * k + out[-1] * (1 - k))
    return out

def rsi(closes, n=14):
    if len(closes) < n + 2:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
    return 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)

def atr(bars, n=14):
    if len(bars) < n + 2:
        return 0.0
    trs = []
    for i in range(1, len(bars)):
        trs.append(max(bars[i]["h"] - bars[i]["l"],
                       abs(bars[i]["h"] - bars[i-1]["c"]),
                       abs(bars[i]["l"] - bars[i-1]["c"])))
    a = sum(trs[:n]) / n
    for i in range(n, len(trs)):
        a = (a * (n - 1) + trs[i]) / n
    return a

def bollinger(closes, n=20, k=2.0):
    if len(closes) < n:
        return None
    w = closes[-n:]; m = sum(w) / n
    sd = (sum((x - m) ** 2 for x in w) / n) ** 0.5
    return m - k * sd, m, m + k * sd

def pivots(bars, back=2):
    hi, lo = [], []
    for i in range(back, len(bars) - back):
        seg = bars[i - back: i + back + 1]
        if bars[i]["h"] == max(s["h"] for s in seg): hi.append(bars[i]["h"])
        if bars[i]["l"] == min(s["l"] for s in seg): lo.append(bars[i]["l"])
    return hi, lo

def trend(hi, lo):
    """Simple structure read on last pivots."""
    if len(hi) < 3 or len(lo) < 3:
        return "none"
    if hi[-1] > hi[-2] > hi[-3] and lo[-1] > lo[-2] > lo[-3]:
        return "up"
    if hi[-1] < hi[-2] < hi[-3] and lo[-1] < lo[-2] < lo[-3]:
        return "down"
    return "none"

def level_prox(px, levels, a):
    return any(abs(px - lv) <= 0.5 * a for lv in levels)

# ---------- playbook §12 candle library (closed bars only) ----------

REV, CONT = "reversal", "continuation"

def candle_engine(b):
    """Returns [(name, direction, kind)] on the last three CLOSED bars."""
    out = []
    if len(b) < 4:
        return out
    p3, p2, p1 = b[-4], b[-3], b[-2]
    def body(x): return abs(x["c"] - x["o"])
    def rng(x): return max(x["h"] - x["l"], 1e-9)
    def bull(x): return x["c"] > x["o"]
    ub = lambda x: x["h"] - max(x["o"], x["c"])
    lb = lambda x: min(x["o"], x["c"]) - x["l"]
    mid = lambda x: (x["o"] + x["c"]) / 2
    if body(p1) > 0 and lb(p1) >= 2 * body(p1) and ub(p1) <= 0.5 * body(p1):
        out.append(("hammer/takuri", 1, REV))
    if body(p1) > 0 and ub(p1) >= 2 * body(p1) and lb(p1) <= 0.5 * body(p1):
        out.append(("shooting-star", -1, REV))
    if bull(p1) and not bull(p2) and body(p1) > body(p2) and p1["c"] >= mid(p2) and p1["o"] <= p2["c"]:
        out.append(("bull-engulfing", 1, REV))
    if not bull(p1) and bull(p2) and body(p1) > body(p2) and p1["c"] <= mid(p2) and p1["o"] >= p2["c"]:
        out.append(("bear-engulfing", -1, REV))
    if not bull(p2) and not bull(p1) and abs(p1["l"] - p2["l"]) < 0.1 * rng(p2) and bull(p1) is False:
        pass  # tweezers handled below with close-body logic
    if p1["l"] == p2["l"] and p1["l"] < min(p1["o"], p2["o"]):
        out.append(("tweezer-bottom", 1, REV))
    if p1["h"] == p2["h"] and p1["h"] > max(p1["c"], p2["c"]):
        out.append(("tweezer-top", -1, REV))
    if not bull(p2) and not bull(p1) and p1["c"] < p2["l"] and p2["c"] < p1["o"]:
        pass  # (engulfing pair variants covered above)
    if not bull(p3) and bull(p2) and p1["h"] >= p2["h"] and p1["c"] > mid(p2) and p2["h"] < p3["h"]:
        out.append(("piercing-line", 1, REV))
    if bull(p3) and bull(p2) and p2["h"] >= p3["h"] and p2["c"] > p3["c"] and bull(p1):
        pass
    if not bull(p3) and body(p2) < 0.5 * body(p3) and bull(p1) and p1["c"] > mid(p3):
        out.append(("morning-star", 1, REV))
    if bull(p3) and body(p2) < 0.5 * body(p3) and not bull(p1) and p1["c"] < mid(p3):
        out.append(("evening-star", -1, REV))
    if all(bull(x) for x in (p3, p2, p1)) and all(body(x) > 0.55 * rng(x) for x in (p3, p2, p1)):
        out.append(("three-soldiers", 1, CONT))
    if all(not bull(x) for x in (p3, p2, p1)) and all(body(x) > 0.55 * rng(x) for x in (p3, p2, p1)):
        out.append(("three-crows", -1, CONT))
    if bull(p1) and not bull(p2) and bull(p3) and body(p1) > body(p3) and p1["c"] > p3["c"]:
        out.append(("three-outside-up", 1, REV))
    if not bull(p1) and bull(p2) and not bull(p3) and body(p1) > body(p3) and p1["c"] < p3["c"]:
        out.append(("three-outside-down", -1, REV))
    return out

# ---------- self-sizing: Sentry decides its own risk from its recent accuracy ----------

class Sizer:
    """risk = base * (0.5 + accuracy) * score-bump, bounded [min, max].
    Accuracy: weighted rolling hit-rate per skill from trades_log rows (live fills 2x)."""

    def __init__(self, base=100.0, lo=50.0, hi=200.0):
        self.base, self.lo, self.hi = base, lo, hi

    def acc(self, skill, rows):
        w = n = gw = gn = 0.0
        for r in rows[-120:]:
            if not r.get("result"):
                continue
            wt = 2.0 if r.get("fired") else 1.0
            # a scratch (~flat, fees ate it) is half a point, not a loss: treating it as a loss
            # punished the sizer for a trade that lost nothing
            win = 1.0 if r["result"] == "win" else (0.5 if r["result"] == "scratch" else 0.0)
            gn += wt; gw += wt * win
            if r.get("skill") == skill:
                n += wt; w += wt * win
        if n >= 3:
            return w / n
        if gn > 0:
            return (w + 0.5 * gw) / (n + 0.5 * gn)
        return 0.5

    def size(self, skill, score, rows):
        a = self.acc(skill, rows)
        risk = self.base * (0.5 + a) * (1.0 + 0.25 * (score - 4))
        return max(self.lo, min(self.hi, round(risk)))

# ---------- skill evaluation on candles; returns fire-dict candidates ----------

def evaluate_symbol(sym, tf, min_score_fire=3):
    """tf: {'1h': [...], '15m': [...], '1d': [...]} closed-bar dicts. Returns candidate list.
    Each candidate: {skill, otype(buy_limit/sell_limit/buy_stop/sell_stop), entry, sl, tp, score}."""
    h1, m15, d1 = tf.get("1h") or [], tf.get("15m") or [], tf.get("1d") or []
    if len(h1) < 60 or len(m15) < 20 or len(d1) < 12:
        return []
    out = []
    bid = h1[-1]["c"]  # last close as reference price (paper cadence = per cycle)
    c1 = [b["c"] for b in h1]
    a = atr(h1)
    if a <= 0:
        return []
    e20, e50 = ema(c1, 20), ema(c1, 50)
    e20v = e20[-1]
    r15 = rsi([b["c"] for b in m15])
    r5_2 = rsi([b["c"] for b in m15], 2)
    bb = bollinger(c1)
    hi, lo = pivots(h1)
    tr = trend(hi, lo)
    d1c, d1ref = d1[-2]["c"], d1[-12]["c"]
    htf = 1 if d1c > d1ref * 1.001 else (-1 if d1c < d1ref * 0.999 else 0)
    levels = list(hi[-3:]) + list(lo[-3:]) + [e20v]
    near = level_prox(bid, levels, a)

    def push(skill, otype, entry, sl, tp, score):
        if score >= min_score_fire and abs(entry - sl) > 0:
            out.append({"skill": skill, "otype": otype, "entry": round(entry, 8),
                        "sl": round(sl, 8), "tp": round(tp, 8), "score": score})

    # S1 trend pullback
    if tr == "down" and e20v > bid + 0.05 * a and abs(e20v - bid) < 0.9 * a and 40 <= r15 <= 55:
        sl = (hi[-1] if hi else e20v + a) + 0.25 * a
        if sl > e20v:
            push("S1-pullback-short", "sell_limit", e20v, sl, e20v - 1.5 * (sl - e20v), 4 if near else 3)
    if tr == "up" and e20v < bid - 0.05 * a and abs(bid - e20v) < 0.9 * a and 45 <= r15 <= 60:
        sl = (lo[-1] if lo else e20v - a) - 0.25 * a
        if sl < e20v:
            push("S1-pullback-long", "buy_limit", e20v, sl, e20v + 1.5 * (e20v - sl), 4 if near else 3)
    # S2 breakdown / breakout
    if tr == "down" and lo and 0 <= bid - lo[-1] < 0.35 * a:
        lvl = lo[-1]; sl = (hi[-1] if hi else bid) + 0.25 * a
        if sl > lvl - 0.25 * a:
            e = lvl - 0.25 * a
            push("S2-breakdown-short", "sell_stop", e, sl, e - 1.5 * (sl - e), 4 if near else 3)
    if tr == "up" and hi and 0 <= hi[-1] - bid < 0.35 * a:
        lvl = hi[-1]; sl = (lo[-1] if lo else bid) - 0.25 * a
        e = lvl + 0.25 * a
        push("S2-breakout-long", "buy_stop", e, sl, e + 1.5 * (e - sl), 4 if near else 3)
    # S4 band fades (range only)
    if bb and tr == "none":
        lower, midb, upper = bb
        if bid <= lower * 1.001 and r15 < 32:
            push("S4-band-fade-long", "buy_limit", lower, bid - 0.6 * a, midb, 4 if r15 < 25 else 3)
        if bid >= upper * 0.999 and r15 > 68:
            push("S4-band-fade-short", "sell_limit", upper, bid + 0.6 * a, midb, 4 if r15 > 75 else 3)
    # S18 RSI2 snaps
    if r5_2 < 10 and bid > e20v and tr != "down":
        push("S18-rsi2-long", "buy_limit", bid, bid - 1.2 * a, bid + 1.5 * a, 4 if near else 3)
    if r5_2 > 90 and bid < e20v and tr != "up":
        push("S18-rsi2-short", "sell_limit", bid, bid + 1.2 * a, bid - 1.5 * a, 4 if near else 3)
    # S11 Donchian
    sig1 = h1[-2]
    for n, tag in ((20, "S11-dc20"), (55, "S11-dc55")):
        ch = h1[-(n + 1):-2]
        if len(ch) < 10:
            continue
        hh = max(x["h"] for x in ch); ll = min(x["l"] for x in ch)
        if sig1["c"] > hh and htf >= 0:
            push(f"{tag}-long", "buy_stop", hh + 0.1 * a, hh - 0.6 * a, hh + 2.2 * a, 4 if htf > 0 else 3)
        if sig1["c"] < ll and htf <= 0:
            push(f"{tag}-short", "sell_stop", ll - 0.1 * a, ll + 0.6 * a, ll - 2.2 * a, 4 if htf < 0 else 3)
    # §12 candle library on 1h + 15m closed bars
    for bars, tflabel in ((h1, "H1"), (m15, "M15")):
        a_tf = atr(bars) or a   # stop geometry must follow the bar it is drawn on, not the hour
        for name, direction, kind in candle_engine(bars):
            if len(bars) < 4:
                continue
            last = bars[-2]  # last closed
            if kind == REV:
                if direction == 1 and tr == "up": continue
                if direction == -1 and tr == "down": continue
            else:
                if direction == 1 and tr == "down": continue
                if direction == -1 and tr == "up": continue
            at_lvl = level_prox((last["h"] + last["l"]) / 2, levels, a)
            avg_body = sum(abs(x["c"] - x["o"]) for x in m15[-20:]) / max(len(m15[-20:]), 1)
            big = abs(last["c"] - last["o"]) > (avg_body if tflabel == "M15" else 0.5 * a)
            close_ext = (direction == 1 and last["c"] > (last["h"] + last["l"]) / 2) or \
                        (direction == -1 and last["c"] < (last["h"] + last["l"]) / 2)
            score = sum([at_lvl, big, close_ext, htf in (0, direction), True])
            if direction == 1:
                e = last["h"] + 0.1 * a_tf; sl = last["l"] - 0.25 * a_tf
                push(f"C-{tflabel}-{name}", "buy_stop", e, sl, e + 1.5 * (e - sl), score)
            else:
                e = last["l"] - 0.1 * a_tf; sl = last["h"] + 0.25 * a_tf
                push(f"C-{tflabel}-{name}", "sell_stop", e, sl, e - 1.5 * (sl - e), score)
    return out
