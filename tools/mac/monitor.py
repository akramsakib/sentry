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
    fails = [l for l in reversed(_tail(os.path.join(ROOT, "sentry_journal.md"), 400))
             if "SEND FAILED" in l or "CHECK/SEND FAILED" in l]
    # `bridge` is what the FX build itself concluded on its last cycle — it only exists once that build
    # publishes it, and its absence is shown as "not reported", never as "up". A dashboard that invents
    # an ok is the exact failure this card exists to prevent.
    bridge = st.get("bridge") or "not reported by the build"
    return {"updated": time.strftime("%Y-%m-%d %H:%M KL", time.gmtime(time.time() + 8 * 3600)),
            "book": "forex (MT5)", "execution": "MT5 via the terminal bridge",
            "state": "resident" if (orders or items) else "idle",
            "money": bool(desk.get("entries_enabled")), "n_pendings": len(orders),
            "n_positions": items,
            "positions_label": "desk book items (the terminal's own position count is not read here)",
            "equity": None, "positions": [], "pendings": [],
            "grades": _record(os.path.join(ROOT, "trades_log.jsonl")),
            "events": [l[-160:] for l in jl[:5]],
            "last_scan": scan.split("**")[-1].strip()[-190:] if scan else "",
            "cycle_s": None, "blocked_on": [],
            "sizing": {"base_risk": 125, "live_max_risk": None}, "cost": {},
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
        L.append(f"- open **{b.get('n_positions', len(b.get('positions') or []))}**"
                 + (f" _({b['positions_label']})_" if b.get("positions_label") else "")
                 + f" · pendings **{b.get('n_pendings', len(b.get('pendings') or []))}** · "
                   f"risk on pendings ${_fmt(b.get('at_risk'))} · per-trade ${_fmt(sz.get('base_risk'), 0)}")
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
        poss = b.get("positions") or []
        if poss:
            L += ["", "| position | side | qty | entry | last | R in flight | to stop | $ to stop | PnL |",
                  "|---|---|---|---|---|---|---|---|---|"]
            for p in poss:
                L.append(f"| {p['sym']} {p.get('skill','')} | {p['side']} | {_fmt(p['qty'], 6)} | "
                         f"{_fmt(p['entry'], 6)} | {_fmt(p['last'], 6)} | **{p['r_live']}R** | "
                         f"{p['r_to_stop']}R | ${_fmt(abs(p['pnl']) / max(abs(p['r_live']), 0.001))} | "
                         f"{_fmt(p['pnl'], 2, True)} |")
        pens = b.get("pendings") or []
        if pens:
            L += ["", "| pending | type | entry | stop | target | score | risk | notional |",
                  "|---|---|---|---|---|---|---|---|"]
            for p in pens:
                L.append(f"| {p['sym']} {p.get('skill','')} | {p['type']} | {_fmt(p['entry'], 6)} | "
                         f"{_fmt(p['sl'], 6)} | {_fmt(p['tp'], 6)} | {p.get('score')} | "
                         f"${_fmt(p.get('risk'), 0)} | ${_fmt(p.get('notional'), 0)} |")
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
                 + f' · open <b>{esc(b.get("n_positions", len(b.get("positions") or [])))}</b>'
                   + (f' <span style="font-size:10px">({esc(b["positions_label"])})</span>'
                      if b.get("positions_label") else "")
                   + f' · pendings <b>{esc(b.get("n_pendings", len(b.get("pendings") or [])))}</b></p>')
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
        poss = b.get("positions") or []
        if poss:
            h.append("<table><tr><th>pos</th><th>side</th><th class=n>qty</th><th class=n>entry</th>"
                     "<th class=n>last</th><th class=n>R</th><th class=n>→stop</th><th class=n>PnL</th></tr>")
            for p in poss:
                rcls = "pos" if p["r_live"] > 0 else ("neg" if p["r_live"] < 0 else "")
                h.append(f'<tr><td>{esc(p["sym"])}<br><span style="color:var(--dim)">{esc(p.get("skill"))}</span></td>'
                         f'<td>{esc(p["side"])}</td><td class=n>{esc(_fmt(p["qty"], 5))}</td>'
                         f'<td class=n>{esc(_fmt(p["entry"], 5))}</td><td class=n>{esc(_fmt(p["last"], 5))}</td>'
                         f'<td class=n {rcls}>{esc(p["r_live"])}R</td><td class=n>{esc(p["r_to_stop"])}R</td>'
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
                         f'<td class=n>{esc(p.get("score"))}/5</td><td class=n>${esc(_fmt(p.get("risk"), 0))}</td></tr>')
            h.append("</table>")
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
