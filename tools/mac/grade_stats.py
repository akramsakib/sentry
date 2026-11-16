"""grade_stats — ONE definition of "how often this book wins", shared by every Hermes dashboard.

Why a shared module instead of each page doing its own maths: the sizer already reads a WEIGHTED accuracy
from the same log (live fills count 2x, scratches 0.5), so a dashboard that quietly re-derives a plain
ratio would print a different number from the one that sets position size — and every argument then starts
from a mismatch. Both numbers are therefore produced here, side by side, from one pass over one file, and
both dashboards print the same `line()`.

Definitions, stated so they can be argued with:
  graded    — rows with a `result` at all
  wins / losses / scratch — result == win / loss / anything else (±0.05 R voids, `scratch`)
  decisive  — wins + losses.  A VOID IS NOT A LOSS and not a win, so the honest win rate divides by this.
  win_rate  — wins / decisive, None when there are no decisive outcomes (a page must print "—", not 0 %)
  hit_rate  — wins / graded, the stricter reading: every scratch counts against you. Kept because the desk
              pill and the grading note have always quoted it, and dropping it would change the meaning of
              an existing figure without anyone agreeing to it.
"""
import json

KEYS = ("graded", "wins", "losses", "scratch", "decisive", "net_r", "win_rate", "hit_rate",
        "fired", "by_skill", "line", "note")


def rows_from(path):
    """Tolerant reader: a half-written line at the moment the book appends must never blank a dashboard."""
    out = []
    try:
        with open(path, "r", errors="replace") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                if isinstance(r, dict):
                    out.append(r)
    except Exception:
        pass
    return out


def _num(v, d=0.0):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return d
    return f if f == f else d          # NaN guard: a NaN R would poison net_r silently


def stats(trade_rows):
    # Defensive on purpose: callers hand this parsed lines (rows_from already filters), a fixture hands it
    # a raw string to prove it survives, and a crash inside a stats function takes the whole page down.
    trade_rows = [r for r in trade_rows if isinstance(r, dict)]
    g = [r for r in trade_rows if r.get("result")]
    wins = sum(1 for r in g if r["result"] == "win")
    losses = sum(1 for r in g if r["result"] == "loss")
    scratch = len(g) - wins - losses
    decisive = wins + losses
    net_r = round(sum(_num(r.get("R")) for r in g), 2)
    per = {}
    for r in g:                                     # weighted accuracy: exactly what the sizer consumes
        k = r.get("skill") or "?"
        wt = 2.0 if r.get("fired") else 1.0          # a fill that moved real money counts double
        w = 1.0 if r["result"] == "win" else (0.5 if r["result"] != "loss" else 0.0)
        a = per.setdefault(k, [0.0, 0.0])
        a[0] += wt * w
        a[1] += wt
    by_skill = sorted(({"skill": k, "acc": round(v[0] / v[1], 3), "n": int(v[1])}
                       for k, v in per.items() if v[1] >= 3), key=lambda x: -x["acc"])
    return {"graded": len(g), "wins": wins, "losses": losses, "scratch": scratch,
            "decisive": decisive, "net_r": net_r,
            "win_rate": round(wins / decisive, 4) if decisive else None,
            "hit_rate": round(wins / len(g), 4) if g else None,
            "fired": sum(1 for r in trade_rows if r.get("fired")),
            "by_skill": by_skill[:8],
            "line": line(wins, losses, scratch, len(g), net_r),
            "note": ("no graded outcomes yet — the sizer is on its neutral prior and grows from here"
                     if not g else "sizer is reading this book's own outcomes")}


def line(wins, losses, scratch, graded, net_r):
    """The sentence both dashboards print. Same function, so they cannot drift."""
    decisive = wins + losses
    if not graded:
        # A brand-new book must not read as a 0 % record: "no settled trades yet" and "every trade lost"
        # are different facts, and on a dashboard they looked identical.
        return "win rate — · no graded trades yet (every candidate still open or ungraded)"
    if not decisive:
        return "win rate — · 0 decisive of %d graded (voids only, none counted as a loss)" % graded
    pct = 100.0 * wins / decisive
    hit = " · hits %.1f%% of %d graded" % (100.0 * wins / graded, graded) if scratch else ""
    return "win rate %.1f%% (%d of %d decisive)%s · net %+.2fR" % (pct, wins, decisive, hit, net_r)


def with_line(d):
    """Fill in the keys an OLDER publisher did not write, from the counts it DID write.

    A book publishes its grades as a snapshot, and a book whose book_status.py predates the win rate sends
    graded/wins/losses but no line and no ratio. Recomputing THOSE from the published counts is not a second
    definition of win rate — it is this module's formula applied to the same numbers, so a stale JSON still
    displays correctly instead of showing a dash while the log beside it says otherwise.
    """
    d = dict(d or {})
    wins = int(d.get("wins") or 0)
    losses = int(d.get("losses") or 0)
    scratch = int(d.get("scratch") or 0)
    graded = int(d.get("graded") or (wins + losses + scratch))
    decisive = wins + losses
    d.setdefault("graded", graded)
    d.setdefault("decisive", decisive)
    d.setdefault("net_r", 0.0)
    d["win_rate"] = round(wins / decisive, 4) if decisive else None
    d["hit_rate"] = round(wins / graded, 4) if graded else None
    if not d.get("line"):
        d["line"] = line(wins, losses, scratch, graded, float(d.get("net_r") or 0.0))
        if not graded:
            d["note"] = d.get("note") or "log has rows, none graded yet"
    return d


def merge(*stat_dicts):
    """One record across several books: counts add, rates are recomputed from the pooled counts — never
    averaged, because a 1-trade book and a 40-trade book would otherwise count the same."""
    wins = sum(s.get("wins", 0) for s in stat_dicts)
    losses = sum(s.get("losses", 0) for s in stat_dicts)
    scratch = sum(s.get("scratch", 0) for s in stat_dicts)
    graded = sum(s.get("graded", 0) for s in stat_dicts)
    net_r = round(sum(_num(s.get("net_r")) for s in stat_dicts), 2)
    out = {"wins": wins, "losses": losses, "scratch": scratch, "graded": graded,
           "decisive": wins + losses, "net_r": net_r,
           "books": len(stat_dicts),
           "win_rate": round(wins / (wins + losses), 4) if (wins + losses) else None,
           "hit_rate": round(wins / graded, 4) if graded else None}
    out["line"] = line(wins, losses, scratch, graded, net_r)
    out["note"] = "pooled across %d books; rates recomputed from counts" % len(stat_dicts)
    return out
