"""One page for the whole desk: every book, live, on your Mac.

Reads the status file each resident book publishes (~/hermes_sentry/books/<book>.json), plus the forex
build's own state, and renders:

    ~/hermes_sentry/TRADING.html   (self-contained, dark, refreshes every 60 s)
    ~/hermes_sentry/TRADING.md     (same content, for a terminal / the chat channel)

Read-only by design: it never opens a venue connection, never calls MT5, never writes into a book
folder. If it died, the books must keep trading — so it is a *reader*, run by its own launchd job, and
a book's cycle also refreshes it after publishing, which is why the page can be 0–300 s behind a
cycle but is never the reason a cycle fails.

    python3 monitor.py            # rebuild both files
    python3 monitor.py --print    # rebuild and dump the markdown to stdout
"""
import glob
import sys
import html
import json
import os
import time

ROOT = os.path.expanduser("~/hermes_sentry")
BOOKS = os.path.join(ROOT, "books")
HTML_F = os.path.join(ROOT, "TRADING.html")
MD_F = os.path.join(ROOT, "TRADING.md")
REFRESH_S = 60


# The sibling module is found by the folder THIS file lives in: launchd runs these from the book folder and
# the tests load them by path, so neither __file__-relative sys.path nor cwd can be trusted alone.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    import grade_stats as _gs        # same folder in the repo, same folder on the desk: one file, both pages
except Exception:
    _gs = None                       # never let a missing helper take the page down — the card says so


def _mod():
    """The shared win-rate module, from wherever THIS copy of the desk lives.

    The repo keeps it beside monitor.py, the deployer drops a copy at the desk root and in each book folder,
    and a test loads the module by path. Losing it is never silent: callers get an ``error`` string, which
    both renderers print on the card. A missing maths helper must not turn into a wrong number.
    """
    if _gs is not None:
        return _gs
    import importlib.util
    for cand in (os.path.join(ROOT, "grade_stats.py"), os.path.join(BOOKS, "grade_stats.py"),
                 os.path.join(ROOT, "tools", "mac", "grade_stats.py")):
        if not os.path.isfile(cand):
            continue
        try:
            sp = importlib.util.spec_from_file_location("grade_stats", cand)
            mod = importlib.util.module_from_spec(sp)
            sp.loader.exec_module(mod)
            return mod
        except Exception:
            continue
    return None


def _grades(b):
    """A book's published grades, made display-ready.

    Books publish their grade snapshot, and a book whose book_status.py predates the win rate has counts but
    no ratio and no sentence. with_line() fills those from the SAME module the books use, so one stale
    publisher cannot turn the desk page into a page of dashes.
    """
    g = b.get("grades") or {}
    if not g:
        return {}
    gs = _mod()
    return gs.with_line(g) if gs is not None else dict(g, line=g.get("line") or "win rate —")


MISSING = {"error": "grade_stats.py is not beside monitor.py — win rate NOT computed",
           "graded": 0, "wins": 0, "losses": 0, "scratch": 0, "decisive": 0, "net_r": 0.0,
           "win_rate": None, "hit_rate": None, "fired": 0, "by_skill": [],
           "line": "win rate — (shared module missing)"}


def _record(path):
    """Win rate for a book that publishes no JSON of its own — the forex side, whose trade log is a sibling
    file. Same module as the crypto cards use, so the two halves of one page cannot disagree."""
    gs = _mod()
    if gs is None:
        return dict(MISSING)
    return gs.stats(gs.rows_from(path))


def _json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _tail(path, n=6):
    try:
        with open(path, errors="replace") as f:
            return [l.strip() for l in f.read().splitlines() if l.strip()][-n:]
    except Exception:
        return []


def load_books():
    out = []
    for p in sorted(glob.glob(os.path.join(BOOKS, "*.json"))):
        d = _json(p)
        if isinstance(d, dict) and d.get("book"):
            d["_path"] = p
            ts = d.get("updated_ts")
            if isinstance(ts, (int, float)):
                d["age_min"] = round((time.time() - float(ts)) / 60.0, 1)
                cyc = d.get("cycle_s") or 300
                d["stale"] = d["age_min"] > (2.5 * cyc / 60.0)
            out.append(d)
    out.sort(key=lambda b: (b.get("book") != "crypto", b.get("book") or ""))
    return out


_BOOK_ITEMS = __import__("re").compile(r"book items (\d+)")


def _mark_holders(charts, poss, pens):
    """Tag each chart row with how many of the build's own records hold something on that symbol.

    Computed from the position and pending lists it just published, not from a flag in either one, so the
    matrix and the tables underneath it cannot disagree about who is exposed.
    """
    held = {}
    for p in list(poss) + list(pens):
        sy = p.get("sym")
        if sy:
            held[sy] = held.get(sy, 0) + 1
    for sym in (charts or {}):
        try:
            if charts[sym].get("held") is None:
                charts[sym]["held"] = held.get(sym, 0)
                charts[sym]["_open_fallback"] = True
        except Exception:
            pass                        # a malformed row from an older build must not take the card down
    return charts


def _chart_rows(charts, pbook):
    """One row per symbol x timeframe, straight out of the build's own per-cycle record.

    The point of the matrix is that "no signal" and "not scanned" must not look the same on the page: a
    chart with too few bars is flagged from the build's own shortfall map, and the pattern count is a
    cumulative figure (seen_candles is a rolling 300-key list), so it is labelled as such rather than
    presented as a per-day hit rate.
    """
    need = (pbook or {}).get("bars_needed") or {}
    rows = []
    for sym in sorted(charts or {}):
        c = charts[sym] or {}
        for tf in ((pbook or {}).get("timeframes") or ["M5", "M15", "H1", "H4", "D1"]):
            r = c.get(tf) or {}
            if not r:
                continue
            rows.append({"sym": sym, "tf": tf, "bars": r.get("bars"), "need": need.get(tf),
                         "enough": bool(r.get("enough")), "patterns": r.get("patterns"),
                         "last": r.get("last"), "theme": c.get("theme"),
                         "fired_today": c.get("fired_today"), "fired_rolling": c.get("fired_rolling"),
                         "bid": (c.get("quote") or {}).get("bid"), "ask": (c.get("quote") or {}).get("ask"),
                         "open_pos": c.get("held"), "no_quote": not (c.get("quote") or {}),
                         "resting": c.get("resting"), "held_is_fallback": bool(c.get("_open_fallback")),
                         "short": (c.get("thin") or {}).get(tf)})
    return rows


def fx_section():
    """The MT5 forex build, read the way it is actually readable: its state + journal, no terminal call.

    Note what is NOT counted here. Its state file keeps `known_positions`, which is the list of ticket
    ids it has EVER seen (its own code only ever appends), so a monitor that printed that length as
    "open positions" would show a number that only grows — 25 by the time this was written, against a
    desk book of 5. Real open positions live in the terminal, and monitor.py never calls the terminal
    (that is its whole safety property), so the honest figure is the build's own last `book items N`.
    """
    st = _json(os.path.join(ROOT, "state.json"), {}) or {}
    orders = st.get("orders") or []
    desk = _json(os.path.join(ROOT, "desk_mode.json"), {}) or {}
    jl = _tail(os.path.join(ROOT, "sentry_journal.md"), 40)
    items = None
    for line in reversed(jl):
        m = _BOOK_ITEMS.search(line)
        if m:
            items = int(m.group(1))
            break
    scan = next((l for l in reversed(jl) if "scan ok" in l), "")
    # What the terminal actually is, from the build's own file rather than from my assumption: its
    # header says "(demo account)". A dashboard that printed LIVE off `entries_enabled` alone was
    # claiming money moves when it only claims the code is ALLOWED to send — so read the header, and
    # read the age of the build's own log, and let the card say all three.
    kind = "unknown"
    try:
        head = open(os.path.join(ROOT, "sentry_mac.py")).read(1500).lower()
        if "demo account" in head or "(demo)" in head:
            kind = "demo"
        elif "real account" in head or "live account" in head:
            kind = "live"
    except Exception:
        pass
    out_f = os.path.join(ROOT, "sentry.out.log")
    try:
        feed_age_min = round((time.time() - os.path.getmtime(out_f)) / 60.0, 1)
    except Exception:
        feed_age_min = None
    tail400 = _tail(os.path.join(ROOT, "sentry_journal.md"), 400)   # one read, shared by both tallies
    fails = [l for l in reversed(tail400) if "SEND FAILED" in l or "CHECK/SEND FAILED" in l]
    # `bridge` is what the FX build itself concluded on its last cycle — it only exists once that build
    # publishes it, and its absence is shown as "not reported", never as "up". A dashboard that invents
    # an ok is the exact failure this card exists to prevent.
    bridge = st.get("bridge") or "not reported by the build"
    # ---- current trades + the playbook, chart by chart, as the resident itself publishes them ----
    # state.json used to carry only day-counters (orders/known_positions), so this card could honestly say
    # "book items 12" and nothing else. The build now also writes positions_now / book / charts / playbook
    # each cycle (see publish_watch in sentry_mac.py). Everything below is read out of those fields: no
    # terminal call, no second opinion. If the build is older than that change the fields simply are not
    # there, and each block says so instead of showing an empty table that would read as "no trades".
    charts = st.get("charts") or {}
    pbook = st.get("playbook") or {}
    watch_asof = st.get("watch_asof") or ""
    try:
        book_age_min = round((time.time() - os.path.getmtime(os.path.join(ROOT, "state.json"))) / 60.0, 1)
    except Exception:
        book_age_min = None
    # Best-effort join of a terminal position back to the skill that opened it: the terminal knows only the
    # ticket, the build knows the skill, and the one thing they share is the entry price the order was sent
    # at. Matched against the build's OWN paper records, within 0.1 %. If it does not match, the cell is
    # blank — an unlabelled row is honest, a guessed skill on a live trade is not.
    # Every entry the build journalled as sent, with no order id ever coming back: its send-result regex wants
    # "order": "<digits>" and the terminal does not answer with one, so `ticket ?` is in all 97 of its HIT
    # lines. That is counted here because it is the single most important thing to know before arming this
    # build with real money: an order it cannot look up is an order it cannot prove it placed.
    advisory = [l for l in tail400 if "advisory only" in l]
    hits = [l for l in tail400 if "HIT —" in l]
    no_ticket = sum(1 for l in hits if "ticket ?" in l)
    skill_note = ("no order id ever came back from the terminal, so a position cannot be tied to the skill "
                  f"that opened it ({no_ticket} of {len(hits)} sends the build journalled this way)") \
        if hits else ""
    poss = []
    for p in (st.get("positions_now") or []):
        d = 1.0 if str(p.get("action", "")).lower().startswith("buy") else -1.0
        span = abs((p.get("open") or 0.0) - (p.get("sl") or 0.0))
        r_to = None
        if span:
            r_to = round(((p.get("last", 0.0) - p.get("sl", 0.0)) if d > 0
                          else (p.get("sl", 0.0) - p.get("last", 0.0))) / span, 2)
        poss.append({"sym": p.get("sym"), "skill": "",
                     "side": p.get("action"), "qty": p.get("vol"), "entry": p.get("open"),
                     "last": p.get("last"), "r_live": p.get("r_now"), "r_to_stop": r_to,
                     "pnl": p.get("profit"), "sl": p.get("sl"), "tp": p.get("tp"),
                     "ticket": p.get("id"), "age_min": p.get("age_min")})
    book = ((st.get("book") or {}).get("items")) or []
    pens = []
    for o in book:
        if str(o.get("state", "")).lower() not in ("active", "pending", "placed", "accepted"):
            continue
        pens.append({"sym": o.get("sym"), "skill": "",
                     "type": o.get("type"), "entry": o.get("price"), "sl": None, "tp": None,
                     "score": None, "risk": next((x.get("risk") for x in reversed(orders)
                                                  if x.get("sym") == o.get("sym")), None),
                     "notional": None, "ticket": o.get("ticket")})
    charts = _mark_holders(charts, poss, pens)
    return {"updated": time.strftime("%Y-%m-%d %H:%M KL", time.gmtime(time.time() + 8 * 3600)),
            "book": "forex (MT5)", "execution": "MT5 via the terminal bridge",
            "state": "resident" if (orders or items) else "idle",
            "money": bool(desk.get("entries_enabled")), "n_pendings": len(orders),
            "n_positions": (len(poss) if st.get("positions_now") is not None else None),
            "positions_label": ("the terminal's own open positions, as the build last read them"
                                if st.get("positions_now") is not None else
                                "desk book items (the terminal's own position count is not read here)"),
            "n_journal_items": items, "watch_published": st.get("positions_now") is not None,
            "skill_note": skill_note, "n_hits": len(hits), "n_no_ticket": no_ticket,
            "pendings_word": "sends today (its day counter)",
            "caps_advisory": bool(advisory), "n_advisory": len(advisory),
            "advisory_last": (advisory[-1][-150:] if advisory else ""),
            "positions_open": st.get("positions_open"), "positions_total_pl": st.get("positions_total_pl"),
            "sends_today": [dict(x) for x in orders][-10:],
            "charts": charts, "chart_rows": _chart_rows(charts, pbook), "playbook": pbook,
            "charts_thin": st.get("charts_thin") or {},
            "watch_asof": watch_asof, "book_age_min": book_age_min,
            "watch_stale": (book_age_min is not None and book_age_min > 15),
            "watch_error": st.get("watch_error") or "", "n_book": len(book), "n_book_pending": len(pens),
            "equity": None, "positions": poss, "pendings": pens,
            "grades": _record(os.path.join(ROOT, "trades_log.jsonl")),
            "events": [l[-160:] for l in jl[:5]],
            "last_scan": scan.split("**")[-1].strip()[-190:] if scan else "",
            "cycle_s": None, "blocked_on": [],
            # The card used to hard-code $125 as this build's per-trade baseline, which was a remembered
            # number, not a read one — and the build self-sizes inside a band, so a single figure was half the
            # story even when it was right. Now the card prints what the build publishes, and if it publishes
            # nothing it prints an em-dash rather than my recollection of a previous version.
            "sizing": ({"base_risk": pbook.get("risk_base"), "band": pbook.get("risk_band"),
                        "source": "published by the build this cycle"}
                       if pbook.get("risk_base") is not None else
                       {"base_risk": None, "band": None,
                        "source": "not published by the build running on the Mac"}),
            "cost": {},
            "fx_only": True, "account_kind": kind, "feed_age_min": feed_age_min,
            "feed_stale": (feed_age_min is not None and feed_age_min > 15),
            "send_fail_last": (fails[0][:150] if fails else ""),
            "send_fail_n": len(fails), "bridge": bridge}


def _money_pill(b):
    """Only ever what the files prove. Three different things were being collapsed into 'LIVE':
    the switch is on, the account is real, and money actually moved. They are not the same claim."""
    if b.get("fx_only"):
        kind = b.get("account_kind") or "unknown"
        acct = {"demo": "DEMO account", "live": "REAL account"}.get(kind, "account kind unknown")
        sw = "switch on" if b.get("money") else "switch OFF"
        if str(b.get("bridge") or "").lower().startswith("down"):
            return (f"BRIDGE DOWN — {acct} · {sw} · quotes may be stale", "hold")
        if b.get("feed_stale"):
            return (f"STALE — {acct} · {sw} · feed {b.get('feed_age_min')} min", "hold")
        return (f"{sw} · {acct}", "live" if (b.get("money") and kind == "live") else "hold")
    if b.get("stale"):
        return (f"STALE — last cycle {b.get('age_min')} min ago", "hold")
    if b.get("money"):
        return ("LIVE — orders are being SENT", "live")
    if b.get("state") == "shadow":
        return ("SHADOW — booked, not sent (no key)", "shadow")
    return (str(b.get("state") or "?"), "shadow")


def _open_count(b):
    """(what to print under "open", the words that qualify it) — and never a bare None.

    Two sources, and the card says which one it used: `positions_now` is the terminal's own list as the build
    read it, while `book items N` is what the build wrote in its journal and covers the whole open book
    (positions and resting orders together). They are different measurements, so both are shown when they
    disagree; what the card must never do is print one of them as if it were the other.
    """
    if b.get("n_positions") is not None:
        return str(b["n_positions"]), b.get("positions_label")
    if b.get("n_journal_items") is not None:
        return str(b["n_journal_items"]), ("the build's own `book items` journal count — positions AND "
                                           "resting orders, not a position count")
    return "—", b.get("positions_label")


def _money_or_dash(label, v, dp=2):
    """`label —` when the figure was never published, `label **$N**` when it was.

    A dash is a claim of ignorance. `$—` or `$0` is a claim about the account, and on a desk that prints a
    ten-dollar book next to a demo one, the difference is the whole difference.
    """
    return label + " —" if v is None else label + " **" + _fmt(v, dp, True) + "**"


def _fmt(v, dp=2, money=False):
    if v is None or v == "":
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    s = f"{f:,.{dp}f}"
    return ("$" + s) if money else s


def to_markdown(books, fx, built):
    L = [f"# Sentry desk — {built}", "",
         f"Refreshed every {REFRESH_S}s by `com.hermes.sentry.monitor`. Read-only over the books' own files.", ""]
    for b in list(books) + [fx]:
        if not b:
            continue
        pill, _ = _money_pill(b)
        L.append(f"## {b['book']} — {pill}")
        L.append("")
        g = _grades(b)
        cost = b.get("cost") or {}
        sz = b.get("sizing") or {}
        L.append(f"- venue `{b.get('execution')}` · state {b.get('state')} · updated {b.get('updated')}"
                 + (f" · cycle {b['cycle_s']}s" if b.get("cycle_s") else ""))
        if b.get("equity") is not None:
            L.append(f"- equity **${_fmt(b.get('equity'))}** · cash ${_fmt(b.get('cash'))} · "
                     f"realized ${_fmt(b.get('realized'))} · fees ${_fmt(b.get('fees_paid'))} · "
                     f"exposure ${_fmt(b.get('exposure'))}")
            # Whoever asks "how much do I have?" reads THIS line, so it may not be allowed to look like an
            # answer about their venue balance: without a key the book cannot query the wallet at all, and
            # every dollar on the card is the simulator's own. Only say it when it is true (money=False).
            if not b.get("money"):
                L.append("- **not your exchange balance** — with no API key this book cannot read your "
                         "wallet, so the figures above are its paper ledger. Your venue balance is only "
                         "visible on the exchange's own page.")
        _n_open, _lbl = _open_count(b)
        L.append(f"- open **{_n_open}**"
                 + (f" _({_lbl})_" if _lbl else "")
                 + f" · {b.get('pendings_word') or 'pendings'} **{b.get('n_pendings', len(b.get('pendings') or []))}**" 
                 + _money_or_dash(" · risk on pendings", b.get("at_risk"))
                 + _money_or_dash(" · per-trade", sz.get("base_risk"), 0))
        if g:
            L.append(f"- **{g.get('line') or 'win rate —'}**"
                     + (f" · own record {g.get('graded', 0)} graded "
                        f"({g.get('wins', 0)}W/{g.get('losses', 0)}L/{g.get('scratch', 0)}S voids)"
                        f" · sizing reads {'this book' if g.get('graded') else 'the neutral prior'}"
                        if not g.get("error") else f" · {g.get('error')}"))
        if cost.get("drag_r") is not None:
            L.append(f"- venue cost {cost.get('drag_r')}R/trade vs cap {cost.get('cap_r')}R → "
                     f"{cost.get('verdict')}")
        if b.get("blocked_on"):
            L.append("- **waiting on:** " + "; ".join(str(x) for x in b["blocked_on"]))
        if b.get("fx_only"):
            pb = b.get("playbook") or {}
            if b.get("watch_asof"):
                L.append(f"- as the build last saw it: **{b['watch_asof']}** "
                         f"(state file {b.get('book_age_min')} min old)")
            elif b.get("watch_published") is False:
                L.append("- open trades and the chart-by-chart playbook are **not published by the build "
                         "running on the Mac** — this page will not guess them; deploy the resident that "
                         "writes `positions_now` / `charts` to get them here")
            if b.get("watch_error"):
                L.append(f"- **the build's own watch block raised this cycle: `{b['watch_error']}`** — the "
                         "scan is unaffected (the guardrails are upstream of the reporting), but the "
                         "figures below may be from the previous cycle")
            if b.get("watch_stale"):
                L.append(f"- **STALE: the forex feed last wrote {b.get('book_age_min')} min ago** — the "
                         "positions and charts below are whatever the build saw then, not now")
            L.append(f"- terminal bridge, per the build itself: **{b.get('bridge')}**")
            L.append(f"- feed last written {b.get('feed_age_min')} min ago · account kind read from "
                     f"`sentry_mac.py`: **{b.get('account_kind')}** · send failures in the last 400 "
                     f"journal lines: {b.get('send_fail_n') or 0}")
            if b.get("send_fail_last"):
                L.append(f"- last send failure: `{b['send_fail_last']}`")
            L.append("- this page never calls the terminal, so it makes no claim that the bridge is "
                     "reachable; the feed age above is the honest liveness signal")
        elif b.get("stale"):
            L.append(f"- **STALE: last cycle was {b.get('age_min')} min ago** — the launchd job or the "
                     f"venue feed needs attention; nothing here can restart it, by design")
        rows = b.get("chart_rows") or []
        if rows:
            L += ["", "**The playbook, chart by chart** — `bars` is what the build has for that chart this "
                      "cycle; `signals` counts the candle-pattern keys it has logged for it (a rolling "
                      "300-key list, cumulative, not a day's hit rate). A row marked `not scanned` had too "
                      "few bars for the checklist to run at all, so it says nothing about the market. "
                      "● marks a symbol the build is currently holding something on. `decided today` is its "
                      "once-a-day key, stamped for a below-gate candidate, a refused entry AND a sent order "
                      "alike — decisions, not orders; `(rolling)` is what is left of that list, which spans "
                      "several days.", "",
                  "| symbol | theme | TF | bars / needed | signals | last bar | decided today | (rolling) |"
                  " bid / ask |",
                  "|---|---|---|---|---|---|---|---|---|"]
            for r in rows:
                cell = (f"{r['bars']} / {r['need']}" if r["enough"]
                        else f"**not scanned** ({r['bars']} / {r['need']})")
                quote = ("NO QUOTE THIS CYCLE" if r.get("no_quote")
                         else f"{_fmt(r['bid'], 5)} / {_fmt(r['ask'], 5)}")
                L.append(f"| {'**● ' if r.get('open_pos') else ''}{r['sym']} | {r['theme']} | {r['tf']} | "
                         f"{cell} | {r['patterns']} | {r['last'] or '—'} | {r['fired_today']} | "
                         f"{r.get('fired_rolling')} | {quote} |")
            held_no_quote = sorted({r["sym"] for r in rows if r.get("no_quote") and r.get("open_pos")})
            if held_no_quote:
                L += ["", "- **a symbol is held but was not quoted this cycle**: " + ", ".join(held_no_quote)
                      + " — its charts answered with nothing while the build carries a position on it. That "
                        "is a fact about the feed, not about the market, and it is the row to look at first."]
        if (b.get("playbook") or {}):
            pb = b["playbook"]
            L += ["", f"- rules the build publishes for itself: cycle {pb.get('cycle_s')}s · per-trade "
                      f"${_fmt(pb.get('risk_base'), 0)} self-scaled inside ${_fmt((pb.get('risk_band') or [0,0])[0], 0)}"
                      f"-${_fmt((pb.get('risk_band') or [0,0])[1], 0)} · max {pb.get('max_orders_day')} "
                      f"sends/day · theme caps {pb.get('theme_cap')} · timeframes {pb.get('timeframes')} · "
                      f"{pb.get('orders')} · {pb.get('red_window')} · {pb.get('candle_library')}"]
            uni = pb.get("universe") or {}
            if uni:
                L.append(f"- universe as resolved from the terminal catalog this cycle: "
                         + ", ".join(f"{k} ({v})" for k, v in sorted(uni.items())))
        if b.get("n_book_pending") is not None and (b.get("n_book") or 0):
            L.append(f"- the book as the build last read it: **{b['n_book']} items**, of which "
                     f"**{b['n_book_pending']} are resting pending orders**; the day's own send count is "
                     f"{b.get('n_pendings')} (a different number on purpose — one is what is on the book, "
                     f"the other is what this build sent today)")
        if b.get("caps_advisory"):
            L.append(f"- **the caps in this build are advisory, not enforced**: {b['n_advisory']} journal "
                     f"line(s) in the last 400 read `advisory only, FULL FREEDOM mode`. The daily and theme "
                     f"numbers above are what it was CONFIGURED to cap, not what stopped it.")
            if b.get("advisory_last"):
                L.append(f"- last such note: `{b['advisory_last']}`")
        if b.get("skill_note"):
            L.append(f"- **which skill opened which trade is not knowable from these files**: {b['skill_note']}"
                     f" — the crypto books carry their own rid per fill; this build does not, so the "
                     f"position table below is labelled by symbol only")
        if b.get("positions_open") is not None and (b.get("positions") or []):
            L.append(f"- floating P/L on the open book, as the build last read it: "
                     f"**{_fmt(b.get('positions_total_pl'), 2, True)}** across {b['positions_open']} "
                     f"position(s)")
        if b.get("n_journal_items") is not None and b.get("n_journal_items") != b.get("n_book"):
            L.append(f"- the build's journal said `book items {b['n_journal_items']}` on its last cycle; "
                     f"the state file it wrote the same cycle reports {b.get('n_book')} — any gap is "
                     f"between two of ITS OWN reads, and both are shown rather than reconciled by me")
        poss = b.get("positions") or []
        if poss:
            L += ["", "| position | side | qty | entry | last | R in flight | to stop | $ to stop | PnL |",
                  "|---|---|---|---|---|---|---|---|---|"]
            for p in poss:
                rl, rs = p.get("r_live"), p.get("r_to_stop")
                dollars = (f"${_fmt(abs(p.get('pnl') or 0) / max(abs(rl), 0.001))}" if isinstance(rl, (int, float))
                           else "—")     # no stop distance => no R scale => no $-per-R, said as a dash not a 0
                L.append(f"| {p['sym']} {p.get('skill','')} | {p['side']} | {_fmt(p['qty'], 6)} | "
                         f"{_fmt(p['entry'], 6)} | {_fmt(p['last'], 6)} | "
                         f"{('**%sR**' % rl) if isinstance(rl, (int, float)) else 'no stop distance'} | "
                         f"{('%sR' % rs) if isinstance(rs, (int, float)) else '—'} | {dollars} | "
                         f"{_fmt(p.get('pnl'), 2, True)} |")
        pens = b.get("pendings") or []
        if pens:
            L += ["", "| pending | type | entry | stop | target | score | risk | notional |",
                  "|---|---|---|---|---|---|---|---|"]
            for p in pens:
                L.append(f"| {' '.join(x for x in [p['sym'], p.get('skill') or ''] if x)} | {p['type']} | "
                         f"{_fmt(p['entry'], 6)} | "
                         f"{_fmt(p.get('sl'), 6)} | {_fmt(p.get('tp'), 6)} | "
                         f"{p.get('score') if p.get('score') is not None else '—'} | "
                         f"{('$' + _fmt(p.get('risk'), 0)) if p.get('risk') is not None else '—'} | "
                         f"{('$' + _fmt(p.get('notional'), 0)) if p.get('notional') is not None else '—'} |")
            L.append("")
            L.append("_Pending rows above come from the book the build read (symbol, type, price) — the "
                     "stop, target and risk per resting order are not in that read, so they are dashes; "
                     "the risk the build allocated today is in its own sends list, below._")
        sends = b.get("sends_today") or []
        if sends:
            L += ["", f"**What this build sent on {str(b.get('watch_asof') or '')[:10]}** — its own day "
                      f"counter, which is what its caps gate reads (`{b.get('n_pendings')}` of its daily "
                      f"limit of "
                      f"{(b.get('playbook') or {}).get('max_orders_day', '—')}):", "",
                  "| symbol | skill | order | risk |", "|---|---|---|---|"]
            for x in sends:
                L.append(f"| {x.get('sym')} | {x.get('skill')} | {x.get('type')} | "
                         f"${_fmt(x.get('risk'), 0)} |")
            L += ["", "_These are orders it asked the terminal to place today, not necessarily orders still "
                      "alive on it — fills and cancels move the book, and the book is the table above._"]
        ev = b.get("events") or []
        if ev:
            L += ["", "```"] + [e[:150] for e in ev] + ["```"]
        L.append("")
    return "\n".join(L).rstrip() + "\n"


CSS = """
:root{--bg:#0b0e13;--card:#121722;--ink:#dfe6f2;--dim:#8b98ae;--live:#ff5c5c;--shadow:#f2b134;--ok:#3ecf8e;--line:#1e2634}
*{box-sizing:border-box}body{margin:0;padding:22px;background:var(--bg);color:var(--ink);
font:14px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}h1{font-size:17px;margin:0 0 2px;letter-spacing:.04em}
h2{font-size:14px;margin:0 0 10px;display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.sub{color:var(--dim);font-size:12px;margin-bottom:18px}
.wrap{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(430px,1fr));align-items:start}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px;overflow:auto}
.pill{font-size:11px;padding:2px 8px;border-radius:999px;border:1px solid;font-weight:700;letter-spacing:.05em}
.pill.live{color:var(--live);border-color:var(--live)}.pill.shadow{color:var(--shadow);border-color:var(--shadow)}
.kv{color:var(--dim);font-size:12px;margin:0 0 8px}.kv b{color:var(--ink);font-weight:600}
.big{font-size:19px;font-weight:700;margin:2px 0 8px}
table{width:100%;border-collapse:collapse;font-size:12px;margin:8px 0}
th{color:var(--dim);text-align:left;font-weight:500;border-bottom:1px solid var(--line);padding:3px 6px}
td{padding:3px 6px;border-bottom:1px solid #171d29;white-space:nowrap}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.pos{color:var(--ok)}.neg{color:var(--live)}.warn{color:var(--shadow)}
ul{margin:6px 0;padding-left:16px}li{font-size:12px;color:var(--dim);margin:2px 0}
.foot{color:var(--dim);font-size:11px;margin-top:16px;border-top:1px solid var(--line);padding-top:10px}
code{background:#0e131c;padding:1px 4px;border-radius:4px}
"""


def to_html(books, fx, built, md_path):
    esc = lambda s: html.escape(str(s if s is not None else ""))

    def card(b):
        pill, cls = _money_pill(b)
        g, cost, sz = _grades(b), b.get("cost") or {}, b.get("sizing") or {}
        h = [f'<div class="card"><h2>{esc(b["book"])} '
             f'<span class="pill {cls}">{esc(pill)}</span>'
             f'<span style="color:var(--dim);font-weight:400;font-size:11px">via <code>{esc(b.get("execution"))}</code></span></h2>']
        h.append(f'<p class="kv">updated <b>{esc(b.get("updated"))}</b>'
                 + (f' · cycle <b>{esc(b.get("cycle_s"))}s</b>' if b.get("cycle_s") else "")
                 + f' · open <b>{esc(_open_count(b)[0])}</b>'
                   + (f' <span style="font-size:10px">({esc(_open_count(b)[1])})</span>'
                      if _open_count(b)[1] else "")
                   + f' · {esc(b.get("pendings_word") or "pendings")} <b>{esc(b.get("n_pendings", len(b.get("pendings") or [])))}</b></p>')
        if b.get("equity") is not None:
            h.append(f'<p class="big">${esc(_fmt(b.get("equity")))} <span style="font-size:11px;'
                     f'color:var(--dim);font-weight:400">equity · cash ${esc(_fmt(b.get("cash")))} · '
                     f'realized ${esc(_fmt(b.get("realized")))} · fees ${esc(_fmt(b.get("fees_paid")))}</span></p>')
        if b.get("equity") is not None and not b.get("money"):
            h.append('<p class="kv"><b>not your exchange balance</b> — no API key, so this book cannot '
                     'read your wallet; these dollars are its paper ledger, and your real balance is only '
                     'on the venue\'s own page</p>')
        if g:
            h.append(f'<p class="kv"><b>{esc(g.get("line") or "win rate —")}</b></p>'
                     + ('' if g.get("error") else
                        f'<p class="kv">own record <b>{esc(g.get("graded", 0))} graded</b> '
                        f'({esc(g.get("wins", 0))}W / {esc(g.get("losses", 0))}L / '
                        f'{esc(g.get("scratch", 0))}S voids) · sizing from '
                        f'<b>{"this book" if g.get("graded") else "neutral prior"}</b></p>'))
        if cost.get("drag_r") is not None:
            v = cost.get("verdict") or ""
            cls2 = "pos" if v.startswith("inside") else "warn"
            h.append(f'<p class="kv">cost <b>{esc(cost.get("drag_r"))}R</b>/trade vs cap '
                     f'<b>{esc(cost.get("cap_r"))}R</b> · <span class="{cls2}">{esc(v)}</span> '
                     f'(maker {esc(_pct(cost.get("maker")))}/taker {esc(_pct(cost.get("taker")))}) · '
                     f'stop {esc(_pct(cost.get("stop_frac")))}</p>')
        if b.get("blocked_on"):
            h.append('<p class="kv warn">waiting on: ' + esc("; ".join(map(str, b["blocked_on"]))) + "</p>")
        if b.get("stale"):
            h.append(f'<p class="kv warn">STALE — last cycle {esc(b.get("age_min"))} min ago '
                     f'(expected every {esc(b.get("cycle_s"))}s). The job is not finishing.</p>')
        if b.get("fx_only"):
            h.append(f'<p class="kv">feed last written <b>{esc(b.get("feed_age_min"))} min ago</b> · '
                     f'account kind, read from <code>sentry_mac.py</code>: <b>{esc(b.get("account_kind"))}</b>'
                     f' · send failures in the last 400 journal lines: <b>{esc(b.get("send_fail_n") or 0)}</b></p>'
                     + (f'<p class="kv warn">last send failure: {esc(b.get("send_fail_last"))}</p>'
                        if b.get("send_fail_last") else "")
                     + '<p class="kv warn">terminal bridge, per the build itself: <b>'
                       + esc(b.get("bridge")) + '</b>. This page never calls the terminal, so that verdict '
                       'is the build\'s own, not a probe by me.</p>')
            if b.get("watch_asof"):
                h.append(f'<p class="kv">as the build last saw it: <b>{esc(b["watch_asof"])}</b> · state '
                         f'file <b>{esc(b.get("book_age_min"))}</b> min old · current trades <b>'
                         f'{esc(b.get("n_positions"))}</b> open · <b>{esc(b.get("n_book_pending"))}</b> '
                         f'pending on the book</p>')
            elif b.get("watch_published") is False:
                h.append('<p class="kv warn">open trades and the chart-by-chart playbook are <b>not '
                         'published by the build running on the Mac</b> — this page will not guess them; '
                         'deploy the resident that writes <code>positions_now</code> / <code>charts</code>'
                         '</p>')
            if b.get("watch_error"):
                h.append(f'<p class="kv warn">the build\'s own watch block raised this cycle: '
                         f'<code>{esc(b["watch_error"])}</code> — the scan is unaffected, the figures below '
                         f'may be from the previous cycle</p>')
            if b.get("watch_stale"):
                h.append(f'<p class="kv warn">STALE — the forex feed last wrote '
                         f'{esc(b.get("book_age_min"))} min ago; what is below is what it saw THEN, not now'
                         f'</p>')
        rows = b.get("chart_rows") or []
        if rows:
            h.append('<table><tr><th>symbol</th><th>theme</th><th>TF</th><th class=n>bars / needed</th>'
                     '<th class=n>signals</th><th>last bar</th><th class=n>decided today</th>'
                     '<th class=n>(rolling)</th><th class=n>bid / ask</th></tr>')
            for r in rows:
                cell = (f'{esc(r["bars"])} / {esc(r["need"])}' if r["enough"]
                        else f'<span class="warn">not scanned</span> ({esc(r["bars"])} / {esc(r["need"])})')
                q = ('<span class="warn">no quote this cycle</span>' if r.get("no_quote")
                     else esc(_fmt(r["bid"], 5)) + " / " + esc(_fmt(r["ask"], 5)))
                h.append(f'<tr><td>{"<b>● </b>" if r.get("open_pos") else ""}{esc(r["sym"])}</td>'
                         f'<td style="color:var(--dim)">{esc(r["theme"])}</td>'
                         f'<td>{esc(r["tf"])}</td><td class=n>{cell}</td><td class=n>{esc(r["patterns"])}</td>'
                         f'<td style="color:var(--dim);font-size:11px">{esc(r["last"] or "—")}</td>'
                         f'<td class=n>{esc(r["fired_today"])}</td>'
                         f'<td class=n style="color:var(--dim)">{esc(r.get("fired_rolling"))}</td>'
                         f'<td class=n>{q}</td></tr>')
            h.append('</table>'
                     '<p class="kv">● marks a symbol the build is holding something on. <code>signals</code> '
                     'counts the candle-pattern keys it has logged for that chart (a rolling 300-key list, '
                     'cumulative — NOT a per-day hit rate). A row reading <span class="warn">not scanned</span> '
                     'had too few bars for the checklist to run, which says nothing about the market. '
                     '<code>decided today</code> is the build\'s once-a-day key count for that symbol, which it '
                     'stamps for a below-gate candidate, a refused entry AND a sent order alike — decisions, '
                     'not orders. <code>(rolling)</code> is everything left in that list, spanning several '
                     'days.</p>')
            nh = sorted({r["sym"] for r in rows if r.get("no_quote") and r.get("open_pos")})
            if nh:
                h.append('<p class="kv warn"><b>a symbol is held but was not quoted this cycle</b> — '
                         + esc(", ".join(nh)) + '. Its charts answered with nothing while the build carries a '
                         'position on it: that is a fact about the feed, not about the market.</p>')
        if (b.get("playbook") or {}):
            pb = b["playbook"]
            band = pb.get("risk_band") or [0, 0]
            uni = pb.get("universe") or {}
            h.append(f'<p class="kv">rules the build publishes for itself: cycle <b>{esc(pb.get("cycle_s"))}s</b>'
                     f' · per-trade <b>${esc(_fmt(pb.get("risk_base"), 0))}</b> self-scaled inside '
                     f'${esc(_fmt(band[0], 0))}–${esc(_fmt(band[1], 0))} · max '
                     f'<b>{esc(pb.get("max_orders_day"))}</b> sends/day · theme caps '
                     f'<code>{esc(pb.get("theme_cap"))}</code> · TFs <code>{esc(pb.get("timeframes"))}</code> · '
                     f'{esc(pb.get("orders"))} · {esc(pb.get("red_window"))} · {esc(pb.get("candle_library"))}'
                     + (f'<br>universe from the terminal catalog this cycle: '
                        + ", ".join(f'{esc(k)} ({esc(v)})' for k, v in sorted(uni.items())) if uni else "")
                     + '</p>')
        if b.get("caps_advisory"):
            h.append(f'<p class="kv warn"><b>the caps in this build are advisory, not enforced</b> — '
                     f'{esc(b.get("n_advisory"))} journal line(s) in the last 400 read '
                     f'<code>advisory only, FULL FREEDOM mode</code>. The daily and theme numbers above are '
                     f'what it was configured to cap, not what stopped it.</p>'
                     + (f'<p class="kv" style="color:var(--dim)">last such note: '
                        f'<code>{esc(b.get("advisory_last"))}</code></p>'
                        if b.get("advisory_last") else ""))
        if b.get("skill_note"):
            h.append('<p class="kv warn"><b>which skill opened which trade is not knowable from these '
                     'files</b> — ' + esc(b["skill_note"]) + '. The crypto books carry their own rid per '
                     'fill; this build does not, so the position table is labelled by symbol only.</p>')
        if b.get("positions_open") and (b.get("positions") or []):
            h.append(f'<p class="big">{esc(_fmt(b.get("positions_total_pl"), 2, True))}'
                     f'<span style="font-size:12px;color:var(--dim)"> floating P/L across '
                     f'{esc(b["positions_open"])} open position(s), as the build last read it</span></p>')
        if (b.get("n_book") or 0):
            h.append(f'<p class="kv">book as the build last read it: <b>{esc(b["n_book"])}</b> items, of which'
                     f' <b>{esc(b.get("n_book_pending"))}</b> are resting pending orders · this build\'s own'
                     f' sends today: <b>{esc(b.get("n_pendings"))}</b> (deliberately a different number: one'
                     f' is what is on the book, the other is what it sent today)</p>')
        poss = b.get("positions") or []
        if poss:
            h.append("<table><tr><th>pos</th><th>side</th><th class=n>qty</th><th class=n>entry</th>"
                     "<th class=n>last</th><th class=n>R</th><th class=n>→stop</th><th class=n>PnL</th></tr>")
            for p in poss:
                rl, rs = p.get("r_live"), p.get("r_to_stop")
                rcls = ("pos" if rl > 0 else ("neg" if rl < 0 else "")) if isinstance(rl, (int, float)) else ""
                rtxt = (f'{esc(rl)}R' if isinstance(rl, (int, float)) else "no stop distance")
                stxt = (f'{esc(rs)}R' if isinstance(rs, (int, float)) else "—")
                h.append(f'<tr><td>{esc(p["sym"])}<br><span style="color:var(--dim)">{esc(p.get("skill"))}</span></td>'
                         f'<td>{esc(p["side"])}</td><td class=n>{esc(_fmt(p["qty"], 5))}</td>'
                         f'<td class=n>{esc(_fmt(p["entry"], 5))}</td><td class=n>{esc(_fmt(p["last"], 5))}</td>'
                         f'<td class=n {rcls}>{rtxt}</td><td class=n>{stxt}</td>'
                         f'<td class=n>{esc(_fmt(p["pnl"], 0, True))}</td></tr>')
            h.append("</table>")
        pens = b.get("pendings") or []
        if pens:
            h.append("<table><tr><th>pending</th><th>type</th><th class=n>entry</th><th class=n>stop</th>"
                     "<th class=n>target</th><th class=n>score</th><th class=n>risk</th></tr>")
            for p in pens:
                h.append(f'<tr><td>{esc(p["sym"])}<br><span style="color:var(--dim)">{esc(p.get("skill"))}</span></td>'
                         f'<td>{esc(p["type"])}</td><td class=n>{esc(_fmt(p["entry"], 5))}</td>'
                         f'<td class=n>{esc(_fmt(p["sl"], 5))}</td><td class=n>{esc(_fmt(p["tp"], 5))}</td>'
                         f'<td class=n>{(esc(p.get("score")) + "/5") if p.get("score") is not None else "—"}'
                         f'</td><td class=n>{("$" + esc(_fmt(p.get("risk"), 0))) if p.get("risk") is not None else "—"}</td></tr>')
            h.append("</table>")
        pens2 = b.get("sends_today") or []
        if pens2:
            h.append(f'<p class="kv" style="margin-top:10px">what this build sent on '
                     f'<b>{esc(str(b.get("watch_asof") or "")[:10])}</b> — its own day counter, which is '
                     f'what its caps gate reads (<b>{esc(b.get("n_pendings"))}</b> of '
                     f'<b>{esc((b.get("playbook") or {}).get("max_orders_day", "—"))}</b>/day)</p>'
                     '<table><tr><th>symbol</th><th>skill</th><th>order</th><th class=n>risk</th></tr>')
            for x in pens2:
                h.append(f'<tr><td>{esc(x.get("sym"))}</td>'
                         f'<td style="color:var(--dim);font-size:11px">{esc(x.get("skill"))}</td>'
                         f'<td>{esc(x.get("type"))}</td>'
                         f'<td class=n>${esc(_fmt(x.get("risk"), 0))}</td></tr>')
            h.append('</table><p class="kv">those are orders it asked the terminal to place today, not '
                     'necessarily orders still alive on it — fills and cancels move the book, and the book '
                     'is the table above.</p>')
        if b.get("last_scan"):
            h.append(f'<p class="kv">{esc(b["last_scan"])}</p>')
        ev = b.get("events") or []
        if ev:
            h.append("<ul>" + "".join(f"<li>{esc(e[:170])}</li>" for e in ev) + "</ul>")
        h.append("</div>")
        return "".join(h)

    return ("<!doctype html><html><head><meta charset='utf-8'>"
            f"<meta http-equiv='refresh' content='{REFRESH_S}'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Sentry desk</title><style>" + CSS + "</style></head><body>"
            f"<h1>SENTRY DESK</h1><p class='sub'>built {esc(built)} · auto-refresh {REFRESH_S}s · "
            f"read-only over the books' own files · markdown twin at <code>{esc(md_path)}</code></p>"
            "<div class='wrap'>" + "".join(card(x) for x in list(books) + ([fx] if fx else [])) + "</div>"
            "<p class='foot'>SHADOW = the book scans, sizes and books fills against the venue's real "
            "prices but sends nothing; it arms itself the moment its key file has a key in it "
            "(auto_ack_on_key). Nothing here can move money: monitor.py never opens a venue "
            "connection, never calls the terminal, and never writes into a book folder.</p>"
            "</body></html>")


def _pct(v):
    try:
        return f"{100 * float(v):.2f}%"
    except (TypeError, ValueError):
        return "—"


def build(pr=False):
    built = time.strftime("%Y-%m-%d %H:%M KL", time.gmtime(time.time() + 8 * 3600))
    books = load_books()
    fx = fx_section()
    md = to_markdown(books, fx, built)
    tmp = MD_F + ".tmp"
    with open(tmp, "w") as f:
        f.write(md)
    os.replace(tmp, MD_F)
    tmp = HTML_F + ".tmp"
    with open(tmp, "w") as f:
        f.write(to_html(books, fx, built, MD_F))
    os.replace(tmp, HTML_F)
    if pr:
        print(md)
    else:
        print(f"monitor: {len(books)} crypto book(s) + forex → {HTML_F} ({os.path.getsize(HTML_F)} B), {MD_F}")
    return 0


if __name__ == "__main__":
    raise SystemExit(build("--print" in __import__("sys").argv))
