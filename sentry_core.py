"""Sentry Core — the Mac engine, ported whole. Broker-agnostic, no I/O except the clock.

v4.7.0: this is no longer a subset port. It carries the ENTIRE detector array of the Mac/MT5
build (sentry_mac.py v3.1): the same 22-pattern §12 candle library verbatim, all 16 skill
families (S1, S2, S3, S4, S10, S11, S13, S15, S16, S18x2, S21, S22, S23, S24, S25 + candles),
the same five timeframes (M5/M15/H1/H4/D1), the same thresholds, evaluated in the same order.
What is deliberately NOT copied: the Mac's blind-scan behavior (run_cycle fails red on stale
data), its advisory-only caps (this side refuses hard), and its send-ack bug. The Mac's FX/equity
session gates (red window, T11 window) already exempt crypto in its own code — on a crypto-only
universe they are no-ops, so behavior stays identical without being ported as dead branches.

run_cycle.py feeds closed bars, consumes fire-dicts, broker_*.py executes.
"""
import time

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

# ---------- playbook §12 candle engine — all 22 patterns, ported verbatim from
# sentry_mac v3.1 candle_engine(). Same bars in (t/o/h/l/c/v dicts, oldest first),
# same last-three-CLOSED window, same names, same order. ----------

REV, CONT = "reversal", "continuation"

def candle_engine(b):
    """Returns [(name, dir, kind)] on the last three CLOSED bars."""
    out = []
    if len(b) < 4:
        return out
    p3, p2, p1 = b[-4], b[-3], b[-2]          # last three CLOSED
    def body(x): return abs(x["c"] - x["o"])
    def rng(x): return max(x["h"] - x["l"], 1e-9)
    def bull(x): return x["c"] > x["o"]
    ub = lambda x: x["h"] - max(x["o"], x["c"])
    lb = lambda x: min(x["o"], x["c"]) - x["l"]
    mid = lambda x: (x["o"] + x["c"]) / 2
    # singles
    if body(p1) > 0 and lb(p1) >= 2 * body(p1) and ub(p1) <= 0.5 * body(p1): out.append(("hammer/takuri", 1, REV))
    if body(p1) > 0 and ub(p1) >= 2 * body(p1) and lb(p1) <= 0.5 * body(p1): out.append(("shooting-star", -1, REV))
    if body(p1) <= 0.15 * rng(p1) and lb(p1) >= 0.5 * rng(p1) and ub(p1) <= 0.1 * rng(p1): out.append(("dragonfly", 1, REV))
    if body(p1) <= 0.15 * rng(p1) and ub(p1) >= 0.5 * rng(p1) and lb(p1) <= 0.1 * rng(p1): out.append(("gravestone", -1, REV))
    if body(p1) >= 0.85 * rng(p1): out.append(("marubozu", 1 if bull(p1) else -1, CONT))
    # two-candle
    if bull(p1) and not bull(p2) and p1["c"] > p2["o"] and p1["o"] < p2["c"] and body(p1) > body(p2): out.append(("bull-engulfing", 1, REV))
    if not bull(p1) and bull(p2) and p1["c"] < p2["o"] and p1["o"] > p2["c"] and body(p1) > body(p2): out.append(("bear-engulfing", -1, REV))
    if bull(p1) and not bull(p2) and p1["o"] < p2["l"] and p1["c"] > mid(p2) and p1["c"] < p2["o"]: out.append(("piercing", 1, REV))
    if not bull(p1) and bull(p2) and p1["o"] > p2["h"] and p1["c"] < mid(p2) and p1["c"] > p2["o"]: out.append(("dark-cloud", -1, REV))
    if abs(p1["l"] - p2["l"]) <= 0.2 * min(rng(p1), rng(p2)) and not bull(p2) and bull(p1): out.append(("tweezer-bottom", 1, REV))
    if abs(p1["h"] - p2["h"]) <= 0.2 * min(rng(p1), rng(p2)) and bull(p2) and not bull(p1): out.append(("tweezer-top", -1, REV))
    if bull(p1) and not bull(p2) and body(p1) < body(p2) and p1["o"] > p2["c"] and p1["c"] < p2["o"]: out.append(("bull-harami", 1, REV))
    if not bull(p1) and bull(p2) and body(p1) < body(p2) and p1["o"] < p2["c"] and p1["c"] > p2["o"]: out.append(("bear-harami", -1, REV))
    if not bull(p2) and not bull(p1) and body(p1) < body(p2) and p1["l"] >= p2["l"]: out.append(("homing-pigeon", 1, REV))
    # three-candle
    if not bull(p3) and body(p2) < 0.5 * body(p3) and bull(p1) and p1["c"] > mid(p3): out.append(("morning-star", 1, REV))
    if bull(p3) and body(p2) < 0.5 * body(p3) and not bull(p1) and p1["c"] < mid(p3): out.append(("evening-star", -1, REV))
    if all(bull(x) for x in (p3, p2, p1)) and all(body(x) > 0.55 * rng(x) for x in (p3, p2, p1)): out.append(("three-soldiers", 1, CONT))
    if all(not bull(x) for x in (p3, p2, p1)) and all(body(x) > 0.55 * rng(x) for x in (p3, p2, p1)): out.append(("three-crows", -1, CONT))
    if bull(p1) and not bull(p2) and not bull(p3) and p1["c"] > p3["h"]: out.append(("three-inside-up", 1, REV))
    if not bull(p1) and bull(p2) and bull(p3) and p1["c"] < p3["l"]: out.append(("three-inside-down", -1, REV))
    if bull(p1) and not bull(p2) and bull(p3) and body(p1) > body(p3) and p1["c"] > p3["c"]: out.append(("three-outside-up", 1, REV))
    if not bull(p1) and bull(p2) and not bull(p3) and body(p1) > body(p3) and p1["c"] < p3["c"]: out.append(("three-outside-down", -1, REV))
    return out

# ---------- accuracy-based self-sizing (unchanged: it is the same maths the Mac uses) ----------

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

# ---------- the full skill array on five timeframes; returns fire-dict candidates ----------

def evaluate_symbol(sym, tf, min_score_fire=3, seen=None):
    """tf: {'5m','15m','1h','4h','1d'} closed-bar dicts, oldest→newest. Returns candidate list.
    Each candidate: {skill, otype(buy_limit/sell_limit/buy_stop/sell_stop), entry, sl, tp, score}.

    Body is the Mac scan block line-for-line (same indicator windows, same levels, same entry/
    stop/target geometry, same score bumps, same evaluation order). `seen` is the caller's
    seen_candles list — one shot per (symbol, TF, pattern, bar) exactly like the Mac's state key.
    """
    m5 = tf.get("5m") or []; m15 = tf.get("15m") or []; h1 = tf.get("1h") or []
    h4 = tf.get("4h") or []; d1 = tf.get("1d") or []
    if len(m5) < 25 or len(m15) < 15 or len(h1) < 60 or len(h4) < 30 or len(d1) < 8:
        return []
    out = []
    bid = m5[-1]["c"]                        # freshest closed bar; the Mac's live bid is its proxy
    c1 = [b["c"] for b in h1]
    a = atr(h1)
    if a <= 0:
        return []
    e20 = ema(c1, 20); e50 = ema(c1, 50); e20v = e20[-1]
    r15 = rsi([b["c"] for b in m15])
    r5_2 = rsi([b["c"] for b in m5], 2)       # Mac: RSI(2) runs on the 5m closes
    bb = bollinger(c1)
    hi, lo = pivots(h1)
    tr = trend(hi, lo)
    # HTF bias from D1 structure (closed bars)
    d1c = d1[-2]["c"]; d1ref = d1[-12]["c"] if len(d1) >= 12 else d1[0]["c"]
    htf = 1 if d1c > d1ref * 1.001 else (-1 if d1c < d1ref * 0.999 else 0)
    levels = list(hi[-3:]) + list(lo[-3:]) + [e20v]
    near = level_prox(bid, levels, a)
    avg_body = sum(abs(x["c"] - x["o"]) for x in m15[-20:]) / 20

    def push(skill, otype, entry, sl, tp, score):
        # the Mac's fire() applies crypto floor 3 / FX floor 4; this universe is all crypto,
        # and run_cycle passes min_score_fire — same gate, plus the degenerate-stop sanity check
        if score >= min_score_fire and abs(entry - sl) > 0:
            out.append({"skill": skill, "otype": otype, "entry": round(entry, 8),
                        "sl": round(sl, 8), "tp": round(tp, 8), "score": score})

    # ---- S1 trend pullback ----
    if tr == "down" and e20v > bid + 0.05 * a and abs(e20v - bid) < 0.9 * a and 40 <= r15 <= 55:
        sl = (hi[-1] if hi else e20v + a) + 0.25 * a
        if sl > e20v:
            push("S1-pullback-short", "sell_limit", e20v, sl, e20v - 1.5 * (sl - e20v), 4 if near else 3)
    if tr == "up" and e20v < bid - 0.05 * a and abs(bid - e20v) < 0.9 * a and 45 <= r15 <= 60:
        sl = (lo[-1] if lo else e20v - a) - 0.25 * a
        if sl < e20v:
            push("S1-pullback-long", "buy_limit", e20v, sl, e20v + 1.5 * (e20v - sl), 4 if near else 3)
    # ---- S2 breakdown / level continuation ----
    if tr == "down" and lo and 0 <= bid - lo[-1] < 0.35 * a:
        lvl = lo[-1]; sl = (hi[-1] if hi else bid) + 0.25 * a
        if sl > lvl - 0.25 * a:
            e = lvl - 0.25 * a
            push("S2-breakdown-short", "sell_stop", e, sl, e - 1.5 * (sl - e), 4 if near else 3)
    if tr == "up" and hi and 0 <= hi[-1] - bid < 0.35 * a:
        lvl = hi[-1]; sl = (lo[-1] if lo else bid) - 0.25 * a
        e = lvl + 0.25 * a
        push("S2-breakout-long", "buy_stop", e, sl, e + 1.5 * (e - sl), 4 if near else 3)
    # ---- S4/S18 range fades ----
    if bb and tr == "none":
        lower, midb, upper = bb
        if bid <= lower * 1.001 and r15 < 32:
            push("S4-band-fade-long", "buy_limit", lower, bid - 0.6 * a, midb, 4 if r15 < 25 else 3)
        if bid >= upper * 0.999 and r15 > 68:
            push("S4-band-fade-short", "sell_limit", upper, bid + 0.6 * a, midb, 4 if r15 > 75 else 3)
    if r5_2 < 10 and bid > e20v and tr != "down":
        push("S18-rsi2-long", "buy_limit", bid, bid - 1.2 * a, bid + 1.5 * a, 4 if near else 3)
    if r5_2 > 90 and bid < e20v and tr != "up":
        push("S18-rsi2-short", "sell_limit", bid, bid + 1.2 * a, bid - 1.5 * a, 4 if near else 3)
    if abs(bid - e20v) > 2.5 * a:
        if bid < e20v and tr == "none":
            push("S18-ma-revert-long", "buy_limit", bid, bid - 1.0 * a, e20v, 3)
        if bid > e20v and tr == "none":
            push("S18-ma-revert-short", "sell_limit", bid, bid + 1.0 * a, e20v, 3)
    # ---- S10 MA cross (H1 closed) ----
    if len(e20) >= 3 and len(e50) >= 3:
        if e20[-2] <= e50[-2] and e20[-1] > e50[-1] and htf >= 0:
            push("S10-ma-cross-long", "buy_stop", bid + 0.2 * a, bid - 1.2 * a, bid + 2.4 * a, 4 if htf > 0 else 3)
        if e20[-2] >= e50[-2] and e20[-1] < e50[-1] and htf <= 0:
            push("S10-ma-cross-short", "sell_stop", bid - 0.2 * a, bid + 1.2 * a, bid - 2.4 * a, 4 if htf < 0 else 3)
    # ---- S11 Donchian 20/55 (H1 closed) ----
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
    # ---- S13 Ichimoku proxy (H1) ----
    if len(h1) >= 30:
        tenkan = (max(x["h"] for x in h1[-10:-1]) + min(x["l"] for x in h1[-10:-1])) / 2
        kijun = (max(x["h"] for x in h1[-27:-1]) + min(x["l"] for x in h1[-27:-1])) / 2
        cloud = (max(x["h"] for x in h1[-53:-1]) + min(x["l"] for x in h1[-53:-1])) / 2 if len(h1) >= 54 else kijun
        if tenkan > kijun and bid > cloud and sig1["c"] > tenkan:
            push("S13-ichimoku-long", "buy_stop", bid + 0.15 * a, kijun - 0.3 * a, bid + 2.2 * a, 4 if htf > 0 else 3)
        if tenkan < kijun and bid < cloud and sig1["c"] < tenkan:
            push("S13-ichimoku-short", "sell_stop", bid - 0.15 * a, kijun + 0.3 * a, bid - 2.2 * a, 4 if htf < 0 else 3)
    # ---- S15 squeeze + S16 inside compression ----
    if bb:
        avg_rng = sum(x["h"] - x["l"] for x in h1[-60:]) / 60
        if (sig1["h"] - sig1["l"]) < 0.6 * avg_rng and sig1["c"] > bb[2]:
            push("S15-squeeze-long", "buy_stop", bb[2] + 0.1 * a, bb[1], bb[2] + 2 * (bb[2] - bb[1]), 4)
        if (sig1["h"] - sig1["l"]) < 0.6 * avg_rng and sig1["c"] < bb[0]:
            push("S15-squeeze-short", "sell_stop", bb[0] - 0.1 * a, bb[1], bb[0] - 2 * (bb[1] - bb[0]), 4)
    if len(m15) >= 8:
        p2i, p3i = m15[-2], m15[-3]
        expn = max(m15[-8:-3], key=lambda x: x["h"] - x["l"])
        if (expn["h"] - expn["l"]) > 1.2 * a and p2i["h"] < p3i["h"] and p2i["l"] > p3i["l"]:
            push("S16-inside-long", "buy_stop", p3i["h"] + 0.1 * a, p3i["l"] - 0.25 * a, p3i["h"] + 1.5 * a, 4 if htf >= 0 else 3)
            push("S16-inside-short", "sell_stop", p3i["l"] - 0.1 * a, p3i["h"] + 0.25 * a, p3i["l"] - 1.5 * a, 4 if htf <= 0 else 3)
    # ---- S21 pivot break (prev D1 pivots, M5 confirm) ----
    if len(d1) >= 3:
        pd = d1[-3]
        P = (pd["h"] + pd["l"] + pd["c"]) / 3; R1 = 2 * P - pd["l"]; S1 = 2 * P - pd["h"]
        if m5[-2]["c"] > R1 > bid - a and htf >= 0:
            push("S21-pivot-R1-long", "buy_stop", R1 + 0.1 * a, P, R1 + 2 * (R1 - P), 4 if htf > 0 else 3)
        if m5[-2]["c"] < S1 < bid + a and htf <= 0:
            push("S21-pivot-S1-short", "sell_stop", S1 - 0.1 * a, P, S1 - 2 * (P - S1), 4 if htf < 0 else 3)
    # ---- S3 momentum continuation (playbook S3) ----
    sbar = h1[-2]
    sbar_rng = max(sbar["h"] - sbar["l"], 1e-9)
    if tr == "up" and sbar["c"] > sbar["o"] and sbar["c"] > e20v and e20v > e50[-1] and (sbar["c"] - sbar["o"]) > 0.45 * a and htf >= 0:
        push("S3-momentum-long", "buy_stop", sbar["h"] + 0.1 * a, sbar["l"] - 0.2 * a, sbar["h"] + 2.0 * (sbar_rng + 0.3 * a), 4 if htf > 0 else 3)
    if tr == "down" and sbar["c"] < sbar["o"] and sbar["c"] < e20v and e20v < e50[-1] and (sbar["o"] - sbar["c"]) > 0.45 * a and htf <= 0:
        push("S3-momentum-short", "sell_stop", sbar["l"] - 0.1 * a, sbar["h"] + 0.2 * a, sbar["l"] - 2.0 * (sbar_rng + 0.3 * a), 4 if htf < 0 else 3)
    # ---- S22 RSI divergence reversal (M15 swings) ----
    if len(m15) >= 25:
        swH, swL = [], []
        for i2 in range(2, len(m15) - 2):
            if m15[i2]["h"] > m15[i2-1]["h"] and m15[i2]["h"] > m15[i2+1]["h"] and m15[i2]["h"] >= m15[i2-2]["h"] and m15[i2]["h"] >= m15[i2+2]["h"]:
                swH.append(i2)
            if m15[i2]["l"] < m15[i2-1]["l"] and m15[i2]["l"] < m15[i2+1]["l"] and m15[i2]["l"] <= m15[i2-2]["l"] and m15[i2]["l"] <= m15[i2+2]["l"]:
                swL.append(i2)
        r15c = [b["c"] for b in m15]
        if len(swH) >= 2:
            ia, ib = swH[-2], swH[-1]
            ra = rsi(r15c[:ia+1]); rb = rsi(r15c[:ib+1])
            if m15[ib]["h"] > m15[ia]["h"] and rb < ra - 1 and m15[-2]["c"] < m15[-2]["o"]:
                e = m15[-2]["l"] - 0.1 * a; slx = m15[ib]["h"] + 0.25 * a
                push("S22-rsi-bear-div", "sell_stop", e, slx, e - 1.5 * (slx - e), 4 if htf <= 0 else 3)
        if len(swL) >= 2:
            ia, ib = swL[-2], swL[-1]
            ra = rsi(r15c[:ia+1]); rb = rsi(r15c[:ib+1])
            if m15[ib]["l"] < m15[ia]["l"] and rb > ra + 1 and m15[-2]["c"] > m15[-2]["o"]:
                e = m15[-2]["h"] + 0.1 * a; slx = m15[ib]["l"] - 0.25 * a
                push("S22-rsi-bull-div", "buy_stop", e, slx, e + 1.5 * (e - slx), 4 if htf >= 0 else 3)
    # ---- S23 liquidity sweep: spring / upthrust (Wyckoff) ----
    if len(h1) >= 12:
        sbar = h1[-2]; sbar_rng = max(sbar["h"] - sbar["l"], 1e-9)
        prior_hi = max(x["h"] for x in h1[-11:-2])
        prior_lo = min(x["l"] for x in h1[-11:-2])
        up_wick = sbar["h"] - max(sbar["o"], sbar["c"])
        dn_wick = min(sbar["o"], sbar["c"]) - sbar["l"]
        if sbar["l"] < prior_lo and sbar["c"] > prior_lo and dn_wick > 0.5 * sbar_rng:
            push("S23-spring-long", "buy_stop", sbar["h"] + 0.1 * a, sbar["l"] - 0.25 * a, sbar["h"] + 1.6 * (sbar_rng + 0.35 * a), 4 if htf >= 0 else 3)
        if sbar["h"] > prior_hi and sbar["c"] < prior_hi and up_wick > 0.5 * sbar_rng:
            push("S23-upthrust-short", "sell_stop", sbar["l"] - 0.1 * a, sbar["h"] + 0.25 * a, sbar["l"] - 1.6 * (sbar_rng + 0.35 * a), 4 if htf <= 0 else 3)
    # ---- S24 Fibonacci 0.5-0.618 pullback continuation ----
    if len(hi) >= 1 and len(lo) >= 1 and hi[-1] > lo[-1]:
        lastH, lastL = hi[-1], lo[-1]
        z_lo = lastH - 0.618 * (lastH - lastL); z_hi = lastH - 0.5 * (lastH - lastL)
        if tr == "up" and z_lo <= bid <= z_hi and h1[-2]["c"] > h1[-2]["o"]:
            push("S24-fib-long", "buy_stop", h1[-2]["h"] + 0.1 * a, z_lo - 0.5 * a,
                 h1[-2]["h"] + 1.5 * (max(h1[-2]["h"] - h1[-2]["l"], 1e-9) + 0.4 * a), 4 if htf > 0 else 3)
        z_lo2 = lastL + 0.5 * (lastH - lastL); z_hi2 = lastL + 0.618 * (lastH - lastL)
        if tr == "down" and z_lo2 <= bid <= z_hi2 and h1[-2]["c"] < h1[-2]["o"]:
            push("S24-fib-short", "sell_stop", h1[-2]["l"] - 0.1 * a, z_hi2 + 0.5 * a,
                 h1[-2]["l"] - 1.5 * (max(h1[-2]["h"] - h1[-2]["l"], 1e-9) + 0.4 * a), 4 if htf < 0 else 3)
    # ---- S25 session-range breakout (London 03 / NY 10 server-hour — the Mac reads the clock
    # the same way; on a 24/7 venue this is a liquidity-hour read, not a market-open one) ----
    srv_h = (int((time.time() + 8 * 3600) // 3600) % 24 - 6) % 24
    if srv_h in (9, 16) and len(h1) >= 3:
        anchor = h1[-3]; ah, al = anchor["h"], anchor["l"]
        if ah > al and h1[-2]["c"] > ah and bid > ah and htf >= 0:
            push("S25-session-break-long", "buy_stop", ah + 0.1 * a, al - 0.2 * a, ah + 1.8 * (ah - al + 0.3 * a), 4 if htf > 0 else 3)
        if ah > al and h1[-2]["c"] < al and bid < al and htf <= 0:
            push("S25-session-break-short", "sell_stop", al - 0.1 * a, ah + 0.2 * a, al - 1.8 * (ah - al + 0.3 * a), 4 if htf < 0 else 3)
    # ---- §12 CANDLE LIBRARY on H1 + M15 (closed bars), scored exactly like the Mac ----
    for bars, tflabel in ((h1, "H1"), (m15, "M15")):
        for name, direction, kind in candle_engine(bars):
            sig = bars[-2]
            if kind == REV:
                if direction == 1 and tr == "up": continue
                if direction == -1 and tr == "down": continue
            else:
                if direction == 1 and tr == "down": continue
                if direction == -1 and tr == "up": continue
            key = f"{sym}|{tflabel}|{name}|{sig['t']}"
            if seen is not None:
                if key in seen:
                    continue
                seen.append(key); del seen[:-300]
            at_lvl = level_prox((sig["h"] + sig["l"]) / 2, levels, a)
            big = abs(sig["c"] - sig["o"]) > avg_body if tflabel == "M15" else abs(sig["c"] - sig["o"]) > 0.5 * a
            close_ext = (direction == 1 and sig["c"] > (sig["h"] + sig["l"]) / 2) or \
                        (direction == -1 and sig["c"] < (sig["h"] + sig["l"]) / 2)
            rr_ok = True
            score = sum([at_lvl, big, close_ext, htf in (0, direction), rr_ok])
            skill = f"C-{tflabel}-{name}"
            if direction == 1:
                e = sig["h"] + 0.1 * a; sl = sig["l"] - 0.25 * a
                push(skill, "buy_stop", e, sl, e + 1.5 * (e - sl), score)
            else:
                e = sig["l"] - 0.1 * a; sl = sig["h"] + 0.25 * a
                push(skill, "sell_stop", e, sl, e - 1.5 * (sl - e), score)
    return out
