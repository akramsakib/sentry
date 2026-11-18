#!/usr/bin/env python3
"""Trade Radar — 24/7 monitoring dashboard + alert mailer for the Hermes sentry.

Serves on 0.0.0.0:8790:
  /          live dashboard (auto-refresh)
  /data.json live snapshot (positions, orders, quotes, journal, alerts)
  /embed     compact strip for embedding in other Hermes UIs

Alert pipeline (alerts.outbox written by sentry):
  1. Gmail SMTP if ~/hermes_sentry/gmail_smtp.json exists (chmod 600; fully autonomous)
  2. POST to $HERMES_ALERT_WEBHOOK, i.e. the user's own local automation (n8n), if set
  3. macOS Notification Center (instant, this laptop only)
  Anything not accepted by (1) or (2) stays queued on disk and shows up as "Alerts queued" on the page,
  so a missing channel is visible instead of quietly costing him an alert.
Continuity is launchd's job, not an agent's: com.hermes.radar (KeepAlive) runs this file, and the books
cycle on their own jobs. No Arena session, cookie feed or chat bridge is involved anywhere in this build,
on request (2026-11-17) — the desk used to wake an agent on urgent lines and that coupling is removed.
Digest email every DIGEST_H hours with positions + P&L + recent events + the graded record.
"""
import http.client
import json, os, re, smtplib, socket, subprocess, sys, threading, time
import hashlib
import urllib.error
import urllib.parse
import urllib.request
import base64
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE = "/Users/sakib/hermes_sentry"
PORT = 8790
STATE_F = BASE + "/state.json"
JOURNAL_F = BASE + "/sentry_journal.md"
OUTBOX_F = BASE + "/alerts.outbox"
SENT_F = BASE + "/alerts.sent.log"
NOTED_F = BASE + "/alerts.notified"
DROPPED_F = BASE + "/alerts.dropped"
# The outbox is a sliding window, so what it keeps matters more than how big it is.  Measured on
# 2026-11-18: 200 lines held (the cap), the oldest from 11:08 and the newest from 23:50, and
# alerts.sent.log holding 2 lines — both of them a bridge-drain TEST from 11-17 02:45.  No
# gmail_smtp.json, no HERMES_ALERT_WEBHOOK in the job environment, so nothing has ever been
# delivered off this laptop and every line has been re-queued until the trim threw the oldest away.
# At that rate the queue spends its 200 slots on 116 advisory NOTE lines and drops the 4 FILLs.
# Three fixes, all local, no new secret: an important line is never the one that goes; a line is
# announced once instead of once a minute forever; and what got dropped is counted and shown.
# Why 200 was there: it was not a queue-depth requirement.  The shipped line was a bare
# `remaining[-200:]` inside the rewrite, with no comment and no name, and 200 is this build's house
# number for "recent history" — the resident keeps its day of fired keys with `del done[:-200]` and
# its paper track with `[:-60]`.  It exists so an append-only spool cannot grow without bound: the
# producer never truncates alerts.outbox, only this flush rewrites it.  Nothing about the page depends
# on the size, because the page shows tail(OUTBOX_F, 10).
#
# 200 was also, on its own, losing alerts: measured 200 lines = 29,832 bytes, and the whole held window
# was 13 hours (oldest kept 11:08, newest 23:56), so while no channel was configured anything older
# than half a day was being discarded silently.  Retention costs nothing — 5,000 lines is ~750 KB, and
# while there is no delivery path the spool IS the record — so the window is now 5,000 and the count of
# what overflowed is published either way.  Raise OUTBOX_CAP again if you want more history; nothing
# else in the file assumes a value.
OUTBOX_CAP = 5000
URGENT_PREFIX = ("FILL", "HIT", "CHECK/SEND FAILED", "CANDIDATE", "REFUSED", "HELD", "TRAIL",
                 "BE moved", "SEND ", "[CRYPTO", "DAILY REVIEW", "Sentry online", "margin floor")
SMTP_F = BASE + "/gmail_smtp.json"
CACHE_S = 20
DIGEST_S = 4 * 3600

_cache = {"ts": 0, "data": None}

# ---------------------------------------------------------------- phone access
# He asked to see this dashboard from his phone. It already binds 0.0.0.0, so the only real questions are
# "what URL", "is the Mac's firewall in the way" and "who else on that WiFi can read my positions". The
# answer to the last one: a token, generated on first run, that loopback (this Mac) never needs.
# Where the token lives. Overridable so a test or a second instance cannot write into the live desk
# folder by accident — a shared secret is exactly the kind of file you do not want silently clobbered.
KEY_F = os.environ.get("RADAR_KEY_FILE") or (BASE + "/radar.key")
_key_mem = [None]


def security_key():
    """64-bit URL token, file mode 600, created on first need.

    Not for localhost — nobody types a token into their own machine — but any address that is not loopback
    must present ?k=<key>. If the file cannot be written (read-only volume, a test harness) the key is kept
    in memory and logged, so the gate fails CLOSED rather than open: a dashboard that cannot store its secret
    should not be readable by the whole network.
    """
    if _key_mem[0]:
        return _key_mem[0]
    try:
        k = open(KEY_F).read().strip()
        if len(k) >= 8:
            _key_mem[0] = k
            return k
    except Exception:
        pass
    import secrets
    k = secrets.token_urlsafe(8)
    try:
        with open(KEY_F, "w") as f:
            f.write(k + "\n")
        os.chmod(KEY_F, 0o600)
    except Exception as e:
        print("radar.key not stored (%s) — token is in-memory only and changes on restart" % e, flush=True)
    _key_mem[0] = k
    return k


def lan_ip():
    for iface in ("en0", "en1"):
        try:
            r = subprocess.run(["ipconfig", "getifaddr", iface], capture_output=True, text=True, timeout=4)
            ip = r.stdout.strip()
            if ip.count(".") == 3:
                return ip
        except Exception:
            pass
    return None


def is_local(ip):
    return ip in ("127.0.0.1", "::1", "localhost")


def firewall_state():
    """"reachable" is a fact about the machine, not about this code. The macOS application firewall lets a
    process on the Mac talk to itself but can still refuse an incoming connection from a phone, so the page
    says which it is and hands over the one command that changes it. Never guess this — read it."""
    try:
        r = subprocess.run(["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"],
                           capture_output=True, text=True, timeout=6)
        out = (r.stdout or "").strip()
    except Exception:
        return {"probed": False, "enabled": None, "note": "could not read the firewall state"}
    en = "enabled" in out.lower()
    return {"probed": True, "enabled": en, "raw": out[:80],
            "note": ("macOS firewall is ON: if the page does not open on the phone, add an exception for "
                     "/usr/bin/python3 (needs Touch ID / admin once), or use Tailscale instead of the WiFi IP")
            if en else "firewall off — the WiFi URL should work as-is"}


def tailscale_hint():
    """{"ip":..., "up":bool}. The address belongs to a CONFIGURED tail; whether it can be used right now
    depends on the daemon running, so both facts are reported and the page words them differently."""
    up = None
    try:
        st = subprocess.run(["tailscale", "status"], capture_output=True, text=True, timeout=6)
        up = "Tailscale is stopped" not in (st.stdout or "") and (st.returncode == 0)
    except Exception:
        up = None
    try:
        r = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=6)
        ip = ((r.stdout or "").strip().splitlines() or [""])[0].strip()
    except Exception:
        return None
    return {"ip": ip, "up": up} if ip.count(".") == 3 and ip.startswith("100.") else None



def kl_now():
    return datetime.utcnow() + timedelta(hours=8)

def red_window():
    t = kl_now().hour * 60 + kl_now().minute
    return 20 * 60 + 15 <= t <= 22 * 60 + 30

MCP_BASH = r'''
U="http://127.0.0.1:22346/mcp"
K="$(iconv -f UTF-16LE -t UTF-8 "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/config/assistant.ini" 2>/dev/null | tr -d "\r" | grep -m1 -o "ApiKey=[A-Za-z0-9]*" | cut -d= -f2)"
curl -sS --compressed -D /tmp/hi_radar -o /dev/null --max-time 8 -X POST "$U" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Authorization: Bearer $K" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-06-18\",\"capabilities\":{},\"clientInfo\":{\"name\":\"radar\",\"version\":\"1.0\"}}}"
SID=$(grep -iE "^mcp-session-id:" /tmp/hi_radar | tr -d "\r" | awk "{print \$2}")
curl -sS --compressed -o /dev/null -X POST "$U" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Mcp-Session-Id: $SID" -H "Authorization: Bearer $K" -d "{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}"
echo "@@POS"
curl -sS --compressed -o /tmp/rp -X POST "$U" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Mcp-Session-Id: $SID" -H "Authorization: Bearer $K" -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"get_trading_open_positions\",\"arguments\":{}}}"
sed "s/^data: *//" /tmp/rp | tr -d "\\"
echo "@@QUOTES"
curl -sS --compressed -o /tmp/rq -X POST "$U" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Mcp-Session-Id: $SID" -H "Authorization: Bearer $K" -d "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"get_marketwatch_symbols\",\"arguments\":{}}}"
sed "s/^data: *//" /tmp/rq | tr -d "\\" > /tmp/rqc
for S in XAUUSD EURUSD GBPUSD NVDA AMD; do
grep -o "{ *\"selected\"[^}]*\"symbol\": \"$S\"[^}]*}" /tmp/rqc | head -1 | grep -o "\"bid\": *[0-9.]*\|\"ask\": *[0-9.]*" | tr "\n" " " | sed "s/^/$S /"
echo ""
done
'''

def mcp_snapshot():
    try:
        out = subprocess.run(["bash", "-c", MCP_BASH], capture_output=True, text=True, timeout=30).stdout
    except Exception as e:
        return {"error": str(e)}
    data = {"positions": [], "orders": [], "quotes": {}}
    pos_sec = out.split("@@POS")[-1].split("@@QUOTES")[0] if "@@POS" in out else ""
    for m in re.finditer(r'\{\s*"position_id": "(\d+)", "action": "(\w+)", "reason": "\w+", "symbol": "(\w+)", "create_time": "([^"]+)"[^{}]*?"volume": ([0-9.]+), "price_open": ([0-9.]+), "price_last": ([0-9.]+), "stop_loss": ([0-9.]+), "take_profit": ([0-9.]+),[^{}]*?"profit": (-?[0-9.]+)', pos_sec):
        data["positions"].append({"id": m.group(1), "action": m.group(2), "sym": m.group(3), "time": m.group(4),
                                  "vol": float(m.group(5)), "open": float(m.group(6)), "last": float(m.group(7)),
                                  "sl": float(m.group(8)), "tp": float(m.group(9)), "profit": float(m.group(10))})
    for m in re.finditer(r'\{\s*"order_id": "(\d+)", "order_external_id": "[^"]*", "position_id": "[^"]*", "symbol": "(\w+)", "type": "([\w ]+)"[^{}]*?"state": "(\w+)", "price_order": ([0-9.]+), "stop_loss": ([0-9.]+), "take_profit": ([0-9.]+)', pos_sec):
        data["orders"].append({"id": m.group(1), "sym": m.group(2), "type": m.group(3), "state": m.group(4),
                               "price": float(m.group(5)), "sl": float(m.group(6)), "tp": float(m.group(7))})
    if "@@QUOTES" in out:
        for line in out.split("@@QUOTES")[1].splitlines():
            m = re.match(r'(\S+) "bid": ([0-9.]+) "ask": ([0-9.]+)', line.strip())
            if m: data["quotes"][m.group(1)] = {"bid": float(m.group(2)), "ask": float(m.group(3))}
    return data

# The sibling module is found by the folder THIS file lives in: launchd runs these from the book folder and
# the tests load them by path, so neither __file__-relative sys.path nor cwd can be trusted alone.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    import grade_stats as _gs            # sits beside this file: ~/hermes_sentry/grade_stats.py
except Exception:
    _gs = None                           # a missing helper must degrade the panel, never kill the radar


def _count_lines(path):
    try:
        with open(path) as f:
            return sum(1 for l in f if l.strip())
    except Exception:
        return 0


def record_block():
    """The graded record for every book on the desk, in one place.

    The crypto numbers are PASSED THROUGH from each book's own published JSON — book_status computes them —
    so the radar cannot drift from the desk page. Only the forex log has to be read here, because that
    build writes trades_log.jsonl and no JSON of its own.
    """
    if _gs is None:
        empty = {"error": "grade_stats.py missing next to trade_radar.py — win rate not computed",
                 "graded": 0, "wins": 0, "losses": 0, "scratch": 0, "decisive": 0, "net_r": 0.0,
                 "win_rate": None, "hit_rate": None, "fired": 0, "by_skill": [],
                 "line": "win rate — (shared module missing)"}
        return {"error": empty["error"], "fx": dict(empty), "books": {}, "overall": empty}
    fx = _gs.stats(_gs.rows_from(BASE + "/trades_log.jsonl"))
    books = {}
    d = BASE + "/books"
    try:
        names = sorted(os.listdir(d))
    except Exception:
        names = []
    for fn in names:
        if not fn.endswith(".json"):
            continue
        try:
            j = json.load(open(os.path.join(d + "/" + fn)))
        except Exception:
            continue
        g = j.get("grades") or {}
        if g:
            # with_line: a book whose publisher predates the win rate still shows a correct number, because
            # the ratio is recomputed from ITS OWN published counts, never from a second formula here.
            books[fn[:-5]] = _gs.with_line(g)
    pooled = [fx] + [g for g in books.values() if g.get("graded")]
    return {"fx": fx, "books": books,
            "overall": _gs.merge(*pooled) if pooled else _gs.stats([])}




def money_block(st, rows=None, books_dir=None, day=None):
    """Total trades, wins, losses and the profit or loss, from what each leg ALREADY publishes.

    One rule keeps this honest: a figure is printed only where that leg itself wrote it. The MT5 leg reads the
    resident's `live_record` (its counts are joined on the terminal's own closes) and `account` (kind,
    currency, floating); every crypto leg reads its own `grades` block plus its own `realized`. Nothing here
    re-derives a win rate or a dollar sum from a comment or a second formula, so this table cannot drift from
    the desk page -- `grade_stats` stays the one definition of the ratios, and the money is the account's.

    A count nobody published stays None and the page prints an em dash. Printing 0 for "unknown" would read
    as "it broke even", which is a different claim entirely. A leg that publishes `blocked_on`, or says
    `state: shadow`, is SHADOW: its dollars are shown (hiding them would be worse) but they are never pooled
    into `real_usd`. The account kind is the terminal's own word for itself, so a demo profit cannot be
    misread on a phone as money the desk actually made.
    """
    st = st if isinstance(st, dict) else {}
    lr = st.get("live_record") or {}
    acc = st.get("account") or {}

    def num(v):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return f if f == f else None

    def i(v):
        f = num(v)
        return None if f is None else int(f)

    legs = []
    k = str(acc.get("type") or "unknown").lower()
    fx = {"leg": "MT5 · forex, gold, equities",
          "trades": i(lr.get("sent")), "graded": i(lr.get("graded")),
          "wins": i(lr.get("wins")), "losses": i(lr.get("losses")), "scratch": i(lr.get("scratch")),
          "ungraded": i(lr.get("ungraded")), "net_r": num(lr.get("net_r")),
          "usd": num(lr.get("net_usd")), "floating": num(acc.get("profit")),
          "equity": num(acc.get("equity")), "currency": acc.get("currency") or lr.get("currency") or "",
          "kind": str(acc.get("type") or "unknown"), "login": acc.get("login") or "",
          "server": acc.get("server") or "", "asof": acc.get("asof") or "",
          "shadow": False, "matched": i(lr.get("from_terminal")),
          "real_money": not ("demo" in k or "trial" in k)}
    # `sent` is orders submitted; a book that publishes only graded outcomes has trades == graded.
    if fx["trades"] is None:
        fx["trades"] = fx["graded"]
        fx["trades_is"] = "graded"
    else:
        fx["trades_is"] = "submitted"
    if fx["graded"] is None and fx["trades"] is None:
        fx["note"] = ("no live_record in state.json — the resident on the Mac is older than the ledger "
                      "block, so nothing is claimed here")
    legs.append(fx)

    d = books_dir if books_dir is not None else (BASE + "/books")
    try:
        names = sorted(os.listdir(d))
    except Exception:
        names = []
    for fn in names:
        if not fn.endswith(".json"):
            continue
        try:
            j = json.load(open(os.path.join(d, fn), errors="replace"))
        except Exception:
            continue
        if not isinstance(j, dict):
            continue
        g = j.get("grades") or {}
        pos = [p for p in (j.get("positions") or []) if isinstance(p, dict)]
        # Fail closed on the money claim. Only a book that publishes `state: live` AND no `blocked_on` gets
        # its dollars counted as the account's; a field nobody wrote is treated as shadow, never as proof that
        # a venue key exists. (The producer's guard fails the other way on purpose — an unknown account kind
        # there must trigger the live check, not skip it.)
        shadow = bool(j.get("blocked_on")) or str(j.get("state") or "").lower() != "live"
        fl = sum((num(p.get("pnl")) or 0.0) for p in pos)
        b = {"leg": fn[:-5], "trades": i(g.get("graded")), "graded": i(g.get("graded")),
             "wins": i(g.get("wins")), "losses": i(g.get("losses")), "scratch": i(g.get("scratch")),
             "ungraded": None,
             "net_r": num(g.get("net_r")), "usd": num(j.get("realized")),
             "floating": round(fl, 2) if pos else None, "equity": num(j.get("equity")),
             "currency": j.get("currency") or "USD",
             "kind": str(j.get("state") or ("shadow" if shadow else "unpublished")),
             "login": "", "server": j.get("venue") or "", "asof": j.get("updated") or "",
             "shadow": shadow, "matched": None, "trades_is": "graded", "real_money": not shadow}
        if b["graded"] is None and b["usd"] is None:
            continue        # no ledger and no money in this file: not a leg, so it gets no row
        if b["graded"] is None:
            b["note"] = "money published, no grades block"
        legs.append(b)

    def tot_of(key, only=None):
        vals = [l[key] for l in legs
                if isinstance(l.get(key), (int, float)) and (only is None or bool(l.get("shadow")) == only)]
        return round(sum(vals), 2) if vals else None

    w, l = tot_of("wins"), tot_of("losses")
    # Deliberately absent: no win rate and no pooled net R. grade_stats is the ONE definition of the ratios,
    # and the graded-record table above already prints them for its own population, which is WIDER than this
    # block's (every graded row, not only the trades that were sent). A second headline that differs by its
    # denominator reads as a contradiction, so this block keeps counts and dollars and names its population.
    tot = {"legs": len(legs), "trades": tot_of("trades"), "graded": tot_of("graded"),
           "wins": w, "losses": l, "ungraded": tot_of("ungraded"),
           "usd": tot_of("usd"), "floating": tot_of("floating"), "scratch": tot_of("scratch"),
           "real_usd": tot_of("usd", False), "shadow_usd": tot_of("usd", True),
           "real_trades": tot_of("trades", False), "shadow_trades": tot_of("trades", True),
           "currency": fx["currency"]}
    tot["decisive"] = None if (w is None and l is None) else (w or 0) + (l or 0)
    tot["what"] = ("these are the counts and dollars each leg graded for ITSELF, over the trades it sent; "
                   "the win-rate card above pools every graded row on the desk, sent or not, so the two are "
                   "different populations and are meant to be read that way")
    tot["mixed"] = tot["real_usd"] is not None and tot["shadow_usd"] is not None
    if tot["mixed"]:
        tot["note"] = ("the total pools the terminal leg with shadow books: real leg $%+.2f, shadow legs "
                       "$%+.2f — the shadow dollars are simulated fills, not the account's"
                       % (tot["real_usd"], tot["shadow_usd"]))

    today = {"day": day or "", "graded": None, "usd": None, "wins": None, "losses": None, "ungraded": None}
    if rows is not None:
        t = [r for r in rows if isinstance(r, dict) and r.get("fired")
             and str(r.get("ts") or "")[:10] == (day or "")]
        g = [r for r in t if isinstance(r.get("R"), (int, float))]
        today["graded"] = len(g)
        today["ungraded"] = len(t) - len(g)
        p = [num(r.get("profit")) for r in g]
        p = [x for x in p if x is not None]
        today["usd"] = round(sum(p), 2) if p else 0.0
        # How many rows actually carried a dollar figure: a day where the ledger has R but no profit must
        # print "1 of 3 rows carry a $ figure", not a quiet sum of the two that did.
        today["usd_n"] = len(p)
        today["wins"] = sum(1 for r in g if num(r.get("R")) > 0)
        today["losses"] = sum(1 for r in g if num(r.get("R")) < 0)
        today["net_r"] = round(sum(num(r.get("R")) or 0.0 for r in g), 2) if g else 0.0
    return {"legs": legs, "totals": tot, "today": today, "kind": fx["kind"],
            "real_money": fx["real_money"], "currency": fx["currency"],
            "account_line": st.get("account_line") or ""}


def tail(path, n=12):
    try:
        with open(path) as f: return "".join(f.readlines()[-n:])
    except Exception: return ""

def fx_charts_block(st, now=None):
    """The forex playbook, chart by chart, as the resident itself last recorded it.

    Nothing is fetched here: the block is cut out of the state file snapshot() has ALREADY read, so the radar
    stays exactly as read-only as it was — a hung MetaTrader cannot stall this page, and the numbers cannot
    disagree with the desk page because both read the same published fields. When the build on the Mac is
    older than the per-chart publishing (no `charts` key), the payload says `published: false` and the page
    says so: an empty table would read as "the playbook found nothing", which is a different claim entirely.
    """
    st = st if isinstance(st, dict) else {}
    charts = st.get("charts") or {}
    pb = st.get("playbook") or {}
    tfs = pb.get("timeframes") or ["M5", "M15", "H1", "H4", "D1"]
    need = pb.get("bars_needed") or {}
    rows, thin = [], []
    for sym in sorted(charts):
        c = charts[sym] or {}
        tf = {}
        for t in tfs:
            r = c.get(t) or {}
            if not r:
                continue
            tf[t] = {"bars": r.get("bars"), "enough": bool(r.get("enough")),
                     "pat": r.get("patterns"), "last": r.get("last")}
            if not r.get("enough"):
                thin.append("%s/%s" % (sym, t))
        q = c.get("quote") or {}
        rows.append({"sym": sym, "theme": c.get("theme"), "tf": tf,
                     "fired": c.get("fired_today"), "fired_rolling": c.get("fired_rolling"),
                     "days": c.get("fired_days") or [], "held": c.get("held"),
                     "resting": c.get("resting"), "bid": q.get("bid"), "ask": q.get("ask")})
    try:
        age_min = round(((time.time() if now is None else now) - os.path.getmtime(STATE_F)) / 60.0, 1)
    except Exception:
        age_min = None
    return {"published": bool(charts), "asof": st.get("watch_asof") or "", "tfs": tfs, "need": need,
            "day": st.get("day"),
            "held": {k: v.get("held") for k, v in (charts or {}).items() if v.get("held")},
            "rows": rows, "thin": thin[:12], "error": st.get("watch_error") or "",
            "age_min": age_min, "stale": (age_min is not None and age_min > 15),
            "positions_open": st.get("positions_open"), "book_n": (st.get("book") or {}).get("n"),
            "account": st.get("account") or {}, "live": st.get("live_record") or {},
            "sizing": st.get("sizing") or {},
            "account_line": st.get("account_line") or "",
            "guard_line": st.get("guard_line") or "",
            "live_line": st.get("live_line") or "",
            "rules": {k: pb.get(k) for k in ("cycle_s", "risk_base", "risk_band", "max_orders_day",
                                             "theme_cap", "orders", "red_window", "candle_library") if k in pb}}


def snapshot():
    now = time.time()
    if _cache["data"] and now - _cache["ts"] < CACHE_S:
        return _cache["data"]
    snap = mcp_snapshot()
    try: snap["sentry_state"] = json.load(open(STATE_F))
    except Exception: snap["sentry_state"] = {}
    try: snap["sentry_alive"] = (now - os.path.getmtime(STATE_F)) < 900
    except Exception: snap["sentry_alive"] = False
    snap["journal_tail"] = tail(JOURNAL_F, 12)
    snap["outbox_tail"] = tail(OUTBOX_F, 10)
    snap["kl"] = kl_now().strftime("%Y-%m-%d %H:%M:%S")
    snap["red_window"] = red_window()
    snap["float_pl"] = round(sum(p["profit"] for p in snap.get("positions", [])), 2)
    snap["record"] = record_block()    # Money is the same published fields, read once more so a hung terminal cannot stall it: no fetch,
    # no second formula. `rows is not None` distinguishes "the ledger was read and is empty" from
    # "the shared module is missing", and the page prints a dash for the latter.
    _ss = snap.get("sentry_state") or {}
    snap["money"] = money_block(_ss,
                                _gs.rows_from(BASE + "/trades_log.jsonl") if _gs is not None else None,
                                BASE + "/books", _ss.get("day"))

    snap["fx_charts"] = fx_charts_block(snap.get("sentry_state") or {})
    ip = lan_ip()
    snap["access"] = {"lan_ip": ip, "port": PORT,
                      "phone_url": ("http://%s:%d/?k=%s" % (ip, PORT, security_key())) if ip else None,
                      "tailscale_ip": tailscale_hint(), "firewall": firewall_state(),
                      "token_len": len(security_key())}
    try:
        _ob = [l.rstrip("\n") for l in open(OUTBOX_F) if l.strip()]
    except Exception:
        _ob = []
    snap["channels"] = {"gmail_cfg": os.path.exists(SMTP_F),
                        "notifier": os.path.exists(BASE + "/hermes-notifier"),
                        "webhook": os.environ.get("HERMES_ALERT_WEBHOOK", "").strip()[:60] or None,
                        "queued": len(_ob), "sent": _count_lines(SENT_F),
                        # cap / urgent_held / dropped: what the queue is, not what it should be. If it is
                        # at the cap with nothing urgent held, advisories are being lost and that is a fact
                        # worth a number; the delivery count is the one that says whether mail ever left.
                        "cap": OUTBOX_CAP, "urgent_held": sum(1 for l in _ob if is_urgent(l)),
                        "dropped": _read_dropped(), "full": len(_ob) >= OUTBOX_CAP}
    _cache.update({"ts": now, "data": snap})
    return snap

# ---------------- alert delivery ----------------
def send_gmail(subject, body):
    """Local SMTP only: ~/hermes_sentry/gmail_smtp.json ({"email","app_password","to"}), chmod 600.

    There is no fallback that needs an agent session — if the file is absent, callers see False and the
    dashboard reports "mail: not configured" rather than pretending the alert went out.
    """
    try:
        cfg = json.load(open(SMTP_F))
    except Exception:
        return False
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = cfg["email"]
        msg["To"] = cfg.get("to", cfg["email"])
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as s:
            s.starttls(); s.login(cfg["email"], cfg["app_password"])
            s.sendmail(cfg["email"], [msg["To"]], msg.as_string())
        return True
    except Exception as e:
        print("gmail send failed:", e, flush=True)
        return False

def mac_notify(title, text):
    try:
        subprocess.Popen(["/Users/sakib/hermes_sentry/hermes-notifier",
                          title[:60], text[:140], "http://127.0.0.1:8790"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        try:
            subprocess.run(["osascript", "-e", f'display notification "{text[:120]} (open radar: http://127.0.0.1:8790)" with title "{title[:60]}"'], timeout=5)
        except Exception: pass

def send_webhook(line):
    """POST the alert to the user's own local automation (n8n on his machine, not a bridge).

    Off unless HERMES_ALERT_WEBHOOK is set in this job's environment; a 4 s timeout means a dead
    automation can never stall the alert loop, and a refused POST is simply reported on the page.
    """
    url = os.environ.get("HERMES_ALERT_WEBHOOK", "").strip()
    if not url.startswith("http"):
        return None                              # not configured: a fact to display, not an error
    try:
        req = urllib.request.Request(url, data=json.dumps({"text": line[:1000]}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=4).read()
        return True
    except Exception:
        return False


def alert_body(line):
    """The message, without the "11-18 23:50 KL | " stamp every alert line carries."""
    return line.split(" | ", 1)[1] if " | " in line else line


def is_urgent(line):
    return alert_body(line).startswith(URGENT_PREFIX)


def trim_outbox(lines, cap=OUTBOX_CAP):
    """(kept, n_dropped).  Over the cap, the ADVISORY lines are what gets thrown away, oldest first,
    and a FILL or a refusal is kept even when it is older than the noise that would have evicted it.
    Order is preserved, because the page shows the tail and a shuffled tail reads as a broken clock.
    """
    if len(lines) <= cap:
        return list(lines), 0
    idx_u = [i for i, l in enumerate(lines) if is_urgent(l)]
    idx_o = [i for i, l in enumerate(lines) if not is_urgent(l)]
    keep_u = idx_u[-cap:]
    room = cap - len(keep_u)
    keep_o = idx_o[-room:] if room > 0 else []
    keep = set(keep_u) | set(keep_o)
    kept = [l for i, l in enumerate(lines) if i in keep]
    return kept, len(lines) - len(kept)


def _line_hash(line):
    return hashlib.sha1(line.encode("utf-8", "replace")).hexdigest()[:16]


def _notified():
    try:
        with open(NOTED_F) as f:
            return set(x.strip() for x in f if x.strip())
    except Exception:
        return set()


def _mark_notified(hashes):
    try:
        with open(NOTED_F, "w") as f:
            f.write("\n".join(sorted(hashes)[-OUTBOX_CAP:]) + ("\n" if hashes else ""))
    except Exception:
        pass


def _read_dropped():
    try:
        return int(open(DROPPED_F).read().split()[0])
    except Exception:
        return 0


def _write_dropped(n):
    try:
        with open(DROPPED_F, "w") as f:
            f.write("%d %s\n" % (n, kl_now().strftime("%m-%d %H:%M KL")))
    except Exception:
        pass


def flush_outbox():
    if not os.path.exists(OUTBOX_F): return
    with open(OUTBOX_F) as f: lines = [l.rstrip("\n") for l in f if l.strip()]
    if not lines: return
    remaining = []
    noted = _notified()
    for line in lines:
        # Once per LINE, not once per minute.  This loop runs every 60 s over an undrained queue, so
        # 200 stuck lines meant 200 macOS notifications a minute, forever — and a notification he has
        # seen 800 times is worse than no notification, because it teaches him to ignore the one that
        # matters.  A hash of the line is the watermark: it survives a restart, so the backlog does not
        # re-ping the desk, and a genuinely new event still fires immediately.
        h = _line_hash(line)
        if h not in noted:
            mac_notify("Hermes Trade Alert", line)
            noted.add(h)
        hooked = send_webhook(line)
        # Delivered means SOMETHING OFF THE MAC GOT IT: mail, or his webhook. The notification is local to
        # this laptop and is not counted as delivery, because a laptop is not a channel when he is away.
        # Undelivered lines stay queued on disk — they are never dropped and never need a session.
        if send_gmail("Hermes Trade Alert — " + line[:60], line + "\n\n— Trade Radar / sentry") or hooked is True:
            with open(SENT_F, "a") as f: f.write(line + "\n")
        else:
            remaining.append(line)
    # cap passed explicitly so it is read from the module at flush time, not bound at import:
    # one number at the top of the file to change, and the tests can shrink it to see the overflow.
    kept, dropped = trim_outbox(remaining, OUTBOX_CAP)
    if dropped:
        # Never silently.  The count is on disk and on the page, so "the desk looks fine" cannot be the
        # only evidence that the queue overflowed — the same principle as watch_error on the resident.
        _write_dropped(_read_dropped() + dropped)
    with open(OUTBOX_F, "w") as f: f.write("\n".join(kept) + ("\n" if kept else ""))
    _mark_notified(noted)

def digest_loop():
    last = 0
    while True:
        time.sleep(60)
        flush_outbox()
        if time.time() - last >= DIGEST_S:
            last = time.time()
            s = snapshot()
            pos = "\n".join(f"  {p['sym']} {p['action']} {p['vol']}@{p['open']} last {p['last']} P/L {p['profit']}" for p in s.get("positions", [])) or "  (none)"
            ords = "\n".join(f"  {o['sym']} {o['type']} @{o['price']} sl {o['sl']} tp {o['tp']}" for o in s.get("orders", [])) or "  (none)"
            body = (f"HERMES TRADE RADAR — 4h digest ({s['kl']} KL)\n\n"
                    f"Floating P/L: {s.get('float_pl', 0)}\n\n"
                    f"RECORD: {(s.get('record') or {}).get('overall', {}).get('line', 'win rate —')}\n\n"
                    f"POSITIONS:\n{pos}\n\nWORKING ORDERS:\n{ords}\n\n"
                    f"SENTRY JOURNAL (tail):\n{s.get('journal_tail','')}\n\n— Trade Radar")
            send_gmail(f"Hermes digest — float {s.get('float_pl', 0)} ({s['kl']} KL)", body)


# ---------------------------------------------------------------- cctv: every channel, one tile each
# He asked for the cameras on a second page of the same desk. Two rules here:
#   1. the NVR password stays on this Mac (cctv.json, chmod 600) — the browser is given a proxied
#      /cctv.jpg?ch=N, so the secret never travels to the phone and never appears in a URL;
#   2. a tile is a fact, not a placeholder. An unreachable or unauthenticated camera shows WHY in the tile
#      (401 vs refused vs no config) instead of a fake black square, because a blank CCTV tile reads as
#      "nothing happening" and that is the one lie a camera page is not allowed to tell.
CCTV_F = BASE + "/cctv.json"
try:                       # a bad value must not take the desk down: clamp, never raise
    CCTV_TTL = max(1.0, float(os.environ.get("CCTV_TTL", "8")))
except Exception:
    CCTV_TTL = 8.0
_cctv_cache = {}


def cctv_cfg():
    """{"host":..., "user":..., "password":..., "channels":[{"name":..., "no":1}]} or {} if not configured.

    Deliberately tolerant: a missing file is a normal state (the page explains it), a corrupt one is
    reported with the parse error rather than silently treated as "no cameras".
    """
    out = {"present": os.path.exists(CCTV_F)}
    if not out["present"]:
        return out
    try:
        j = json.load(open(CCTV_F))
    except Exception as e:
        out["error"] = "cctv.json unreadable: %s" % e
        return out
    out.update(j)
    return out


def cctv_discover():
    """Ask the LAN for the box that answers on 37777 (Dahua/NVR's private TCP port) or 554 (RTSP).

    Discovery, not scanning: it reads the Mac's own ARP table and probes those hosts only, so it works on a
    guest VLAN where a sweep would be blocked and it never touches a machine the desk is not already talking to.
    """
    try:
        r = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=8)
        hosts = sorted({w.strip("()") for w in r.stdout.split()
                        if re.fullmatch(r"10*\.\d+\.\d+\.\d+", w.strip("()"))})
    except Exception:
        return {"error": "arp not runnable here", "found": []}
    found = []
    for h in hosts:
        if h.endswith(".1") or h == lan_ip():
            continue
        for port, why in ((37777, "NVR service"), (554, "RTSP"), (80, "web")):
            try:
                sk = socket.create_connection((h, port), timeout=0.35)
                sk.close()
                found.append({"ip": h, "port": port, "what": why})
                break
            except Exception:
                continue
    if found:
        for h in _onvif_probe():
            for f in found:
                if f["ip"] == h["ip"]:
                    f.update({k: v for k, v in h.items() if k != "ip"})
    return {"found": found, "probed": len(hosts)}


def _onvif_parse(data):
    """Pull ip / model / ONVIF endpoint out of a WS-Discovery reply. Pure, so it can be tested on a capture."""
    import re as _r
    t = data.decode("utf-8", "replace")

    def grab(tag):
        m = _r.search("<[^>]*%s[^>]*>([^<]+)" % tag, t)
        return m.group(1).strip() if m else ""

    scopes = grab("Scopes")
    def sc(kind):
        m = _r.search(r"onvif://www.onvif.org/%s/([^ ]+)" % kind, scopes)
        return m.group(1) if m else ""
    ip = grab("XAddrs")
    ip = (_r.search(r"(\d+\.\d+\.\d+\.\d+)", ip) or [None, ""])[1] if ip else ""
    return {"ip": ip, "model": sc("hardware"), "brand": sc("name"), "onvif": grab("XAddrs")[:120]}


def _onvif_probe(timeout=2.5):
    """Ask the LAN who is a camera (WS-Discovery), once. Discovery, not scanning: it multicasts a Hello and
    lists whoever answers - no host is touched that did not announce itself, and it needs no credentials
    because ONVIF discovery is unauthenticated by spec. Only the reply is read; the media service behind it
    still demands a login, which is exactly what the page reports."""
    env = os.environ.get("CCTV_ONVIF", "1")
    if env in ("0", "off", "no"):
        return []
    body = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" '
            'xmlns:a="http://schemas.xmlsoap.org/ws/2003/03/addressing" '
            'xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery" '
            'xmlns:dn="http://www.onvif.org/ver10/network/wsdl"><s:Header><a:Action s:mustUnderstand="1">'
            'http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action>'
            '<a:MessageID>urn:uuid:%s</a:MessageID></s:Header><s:Body>'
            '<d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></s:Body></s:Envelope>'
            % ("%x" % (int(time.time() * 1000) & 0xffffff))).encode()
    out, seen = [], set()
    try:
        sk = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sk.settimeout(0.9)
        sk.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sk.sendto(body, ("239.255.255.250", 3702))
        end = time.time() + timeout
        while time.time() < end and len(out) < 8:
            try:
                d, a = sk.recvfrom(65535)
            except Exception:
                break
            rec = _onvif_parse(d)
            key = (rec.get("ip") or a[0], rec.get("model"))
            if key in seen:
                continue
            seen.add(key)
            rec["ip"] = rec.get("ip") or a[0]
            out.append(rec)
        sk.close()
    except Exception:
        return []
    return out


def _cctv_target(cfg, default_port=None, for_rtsp=False):
    """(host, port) — tolerant of "192.168.0.133", "192.168.0.133:8080" and {"host","port"} alike.

    An NVR on a non-standard web port is normal, and the two ways people write it (colon in host, or a
    separate port key) both have to work for HTTP *and* for the RTSP URL, or the fallback lane builds
    "rtsp://host:8099:554/" and every tile reports a failure that is really our own.
    """
    h = str(cfg.get("host") or "")
    port = None
    if h.count(":") == 1 and h.rsplit(":", 1)[1].isdigit():
        h, port = h.rsplit(":", 1)
        port = int(port)
    if for_rtsp:
        # A port written next to the host is the WEB port. Reusing it for RTSP is how a fallback lane ends up
        # dialling 192.168.0.133:8080 for video and reporting the device as dead, so RTSP only ever honours
        # an explicit "rtsp_port", otherwise 554.
        port = None
    if port is None and cfg.get("port") and not for_rtsp:
        try:
            port = int(cfg.get("port"))
        except Exception:
            port = None
    return h, (port or default_port)


def _cctv_url(cfg, path, default_port=None):
    h, port = _cctv_target(cfg, default_port)
    return "http://%s%s%s" % (h, (":%d" % port) if port else "", path)


def _cctv_privkey(host, user, pw, timeout=6.0, port=None):
    """Dahua's cookie handshake, both spellings, because firmwares disagree on which one they take.

    The web UI asks `GET /privkey/<credential>` and the box answers with a `name=value` string that the page
    then replays as a Cookie — that is the one auth method every Dahua generation accepts, and the only one
    that does not put a password in a header a proxy might log. Two spellings are in the wild (plain
    `user:pw` percent-encoded, and base64 of the same), so both are tried, and a reply with no `=` is
    treated as the value of `logincookie`. The request goes to the recorder and nowhere else; the reply is
    kept in this process only, never in a page, a URL or data.json.
    """
    base = "http://%s%s" % (host, (":%s" % port) if port else "")
    raw = "%s:%s" % (user, pw)
    cands = [urllib.parse.quote(raw, safe=""),
             base64.b64encode(raw.encode()).decode()]
    for cand in cands:
        # urlopen has no `headers=` keyword — a Request does. An earlier draft passed one, both candidates died
        # with TypeError under a bare `except Exception: continue`, and the page blamed the password for a bug
        # three lines away. Catch transport errors only: a fault in this file must not look like a dead camera.
        try:
            rq = urllib.request.Request(base + "/privkey/" + cand, headers={"User-Agent": "hermes-desk/1.0"})
            ck = urllib.request.urlopen(rq, timeout=timeout).read(400).decode("utf-8", "replace").strip()
        except (urllib.error.URLError, OSError, http.client.HTTPException):
            continue
        if not ck or "<" in ck[:1] or len(ck) > 300:
            continue                                   # an HTML login page is not a cookie
        return ck if "=" in ck else ("logincookie=" + ck)
    return None




def _cctv_open(url, cfg, timeout=6.0):
    """One GET, using whichever auth method this firmware actually accepts - and remembering the winner.

    Measured on the office recorder, not assumed: it answers every CGI path with
    `401 WWW-Authenticate: Digest realm="Login to 8be7ed91..."`, so Basic alone is not enough and Digest is
    not a nice-to-have. Order: whatever worked last time, then privkey+Basic, then Digest, then Basic.
    `auth:"none"` in cctv.json skips all of it, which is the mode to use the day a guest/anonymous view is
    enabled on the box - then the desk pulls frames with no credential at all, because it asks the device
    what it allows instead of assuming a login is mandatory.
    """
    parts = urllib.parse.urlsplit(url)
    host, port = parts.hostname, parts.port
    user, pw = cfg.get("user") or "", cfg.get("password") or ""
    want = str(cfg.get("auth") or "auto").lower()
    if want == "none" or not (user and pw):
        return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "hermes-desk/1.0"}),
                                      timeout=timeout)
    order = ["privkey", "digest", "basic"]
    if want in order:
        order = [want]
    elif _cctv_cache.get("_method") in order:
        order = [_cctv_cache["_method"]] + [m for m in order if m != _cctv_cache["_method"]]
    tried = _cctv_cache.setdefault("_tried", [])
    last, last_http = None, None
    realm = "%s://%s" % (parts.scheme, parts.netloc)
    for method in order:
        req = urllib.request.Request(url, headers={"User-Agent": "hermes-desk/1.0"})
        opener = None
        try:
            if method == "privkey":
                # Per host, and only a SUCCESS is remembered. Caching a failure meant one 404 during an NVR
                # reboot (or one write of a different host into cctv.json) left this Mac unable to use the
                # cookie ever again, and a box that needs the cookie then reads as "wrong password".
                jkey = "_jar:" + realm
                if not _cctv_cache.get(jkey):
                    ck = _cctv_privkey(host, user, pw, timeout, port)
                    if ck:
                        _cctv_cache[jkey] = ck
                if _cctv_cache.get(jkey):
                    req.add_header("Cookie", _cctv_cache[jkey])
                import base64
                req.add_header("Authorization", "Basic "
                               + base64.b64encode(("%s:%s" % (user, pw)).encode()).decode())
            else:
                pm = urllib.request.HTTPPasswordMgrWithDefaultRealm()
                pm.add_password(None, realm, user, pw)
                cls = (urllib.request.HTTPDigestAuthHandler if method == "digest"
                       else urllib.request.HTTPBasicAuthHandler)
                opener = urllib.request.build_opener(cls(pm))
            r = opener.open(req, timeout=timeout) if opener else urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            last_http = last_http or e
            last = e
            if e.code not in (401, 403, 407):
                raise
            if method not in tried:
                tried.append("%s(%s)" % (method, e.code))
            continue
        except Exception as e:
            last = e
            if method not in tried:
                tried.append("%s(%s)" % (method, "not offered by this device"
                                             if "scheme" in str(e) else type(e).__name__))
            continue
        _cctv_cache["_method"] = method
        if method not in tried:
            tried.append(method)
        return r
    # the 401 outranks a handler complaint, because "the device refused the login" is the thing he has to
    # act on; "AbstractBasicAuthHandler does not support the scheme: Digest" is a detail of our own library
    raise last_http or last or RuntimeError("no auth method answered")


def _cctv_ffmpeg():
    for cand in (os.environ.get("FFMPEG"), os.path.expanduser("~/.local/bin/ffmpeg"),
                 "/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"):
        if cand and os.path.exists(cand):
            return cand
    return None


def _cctv_rtsp(cfg, ch, timeout=14.0):
    """One frame over RTSP, for the case where this firmware does not serve an HTTP snapshot at all.

    The path is Dahua's own /cam/realmonitor?channel=N&subtype=1 - subtype 1 is the substream, which is what
    a tile should carry: 8 full-resolution streams from one office uplink is how a phone decides the desk is
    broken. Written to a temp file, because the single-frame muxer over a pipe is the part of ffmpeg that
    changes between builds. The credential sits in the argv of a process owned by this user only, and never
    in a page, an image URL, a log line, or data.json.
    """
    ff = _cctv_ffmpeg()
    if not ff:
        raise RuntimeError("no ffmpeg here (checked $FFMPEG, ~/.local/bin, /opt/homebrew/bin, /usr/local/bin)")
    host, rport = _cctv_target(cfg, cfg.get("rtsp_port") or 554, for_rtsp=True)
    user, pw = cfg.get("user") or "", cfg.get("password") or ""
    no = ch.get("no") or 1
    path = ch.get("rtsp") or "/cam/realmonitor?channel=%s&subtype=%s" % (no, cfg.get("subtype", 1))
    auth = ""
    if str(cfg.get("auth") or "auto").lower() != "none" and user and pw:
        auth = "%s:%s@" % (urllib.parse.quote(user, safe=""), urllib.parse.quote(pw, safe=""))
    url = "rtsp://%s%s:%s%s" % (auth, host, rport, path)
    d = BASE + "/.cctv"
    try:
        os.makedirs(d, exist_ok=True)
        os.chmod(d, 0o700)
    except Exception:
        d = "/tmp"
    out = os.path.join(d, "ch%s.jpg" % no)
    try:
        r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-rtsp_transport", "tcp", "-i", url,
                            "-an", "-sn", "-frames:v", "1", "-y", out], capture_output=True, timeout=timeout)
        err = (r.stderr or b"").decode("utf-8", "replace").strip()
    except subprocess.TimeoutExpired:
        raise RuntimeError("rtsp: no frame within %ss (the box accepted the connection and stalled)" % timeout)
    body = b""
    try:
        if os.path.exists(out):
            body = open(out, "rb").read()
        os.unlink(out)
    except Exception:
        pass
    if body[:3] != b"\xff\xd8\xff":
        raise RuntimeError("rtsp: %s" % ((err.splitlines() or ["no frame returned"])[-1])[:110])
    return body


def cctv_probe_anon(cfg, timeout=2.0):
    """What the recorder says to a stranger, so the page can answer "why do you need a login?" with evidence.

    It is one request, only made when there is no credential configured, and it is the difference between
    "the desk wants a password for no reason" and "the device refuses every anonymous path, here is its own
    words". If the answer ever becomes 200, the page starts working without a password and says so.
    """
    host, hport = _cctv_target(cfg, None)
    if not host:
        return None
    url = _cctv_url(cfg, "/cgi-bin/snapshot.cgi?channel=1")
    st = {"url": "/cgi-bin/snapshot.cgi?channel=1"}
    try:
        r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "hermes-desk/1.0"}),
                                   timeout=timeout)
        body = r.read(4096)
        st.update(code=r.status, open=True, anonymous=True, jpeg=body[:3] == b"\xff\xd8\xff",
                  bytes=len(body), ctype=str(r.headers.get("Content-Type")))
        if st["jpeg"]:
            st["note"] = ("this device serves frames to anyone on the LAN - no login needed; set "
                          "\"auth\": \"none\" in cctv.json and the tiles fill in on the next refresh")
        else:
            st["note"] = "answered 200 but not a JPEG (%s) - not a frame source" % st["ctype"]
    except urllib.error.HTTPError as e:
        st.update(code=e.code, open=False, anonymous=False,
                  challenge=str(e.headers.get("WWW-Authenticate") or "")[:70],
                  note="the recorder itself refuses anonymous reads; that is the box being correct")
    except Exception as e:
        st.update(code=None, open=False, error="%s: %s" % (type(e).__name__, str(e)[:70]))
    return st


def cctv_tile(ch, cfg=None):
    """(jpeg_bytes, status_dict). Never raises: a camera that is down is a state to display."""
    cfg = cfg or cctv_cfg()
    st = {"name": ch.get("name") or ("channel %s" % ch.get("no")), "no": ch.get("no"),
          "host": cfg.get("host"), "ok": False, "reason": None, "ts": int(time.time())}
    if not cfg.get("present"):
        st["reason"] = "no cctv.json yet — write the NVR's IP + login into ~/hermes_sentry/cctv.json"
        return None, st
    if cfg.get("error"):
        st["reason"] = cfg["error"]
        return None, st
    if not cfg.get("host"):
        st["reason"] = "cctv.json has no \"host\""
        return None, st
    path = ch.get("snapshot") or "/cgi-bin/snapshot.cgi?channel=%s" % (ch.get("no") or 1)
    mode = str(cfg.get("mode") or "auto").lower()
    if not (cfg.get("user") and cfg.get("password")) and str(cfg.get("auth") or "auto").lower() != "none":
        # Not a black square, not a shrug. The desk asks the recorder what it allows and quotes the answer,
        # so "why does this need a login?" is settled by the device's own 401 rather than by me.
        pr = cctv_probe_anon(cfg) or {}
        st["needs_auth"] = True
        st["anon"] = pr
        ch_401 = " it answers %s%s" % (pr.get("code"), (" " + pr["challenge"]) if pr.get("challenge") else "") \
            if pr.get("code") else ""
        st["reason"] = ("no login in cctv.json. %s" % (pr.get("note") or "the desk has no credential to offer")) + ch_401
        return None, st
    ck = ("tile", st["no"], mode, cfg.get("host"), bool(cfg.get("user")), int(cfg.get("count", 0)))
    ck = (ck, int(st["ts"] // CCTV_TTL))
    if ck in _cctv_cache:
        img, ist = _cctv_cache[ck]
        st.update(ist); st["cached"] = True
        return img, st
    notes, body = [], None
    if mode in ("auto", "http"):
        url = _cctv_url(cfg, path)
        try:
            r = _cctv_open(url, cfg)
            body = r.read()
            st["type"] = r.headers.get("Content-Type", "?")
            if body[:3] != b"\xff\xd8\xff":
                notes.append("http: answered %d B of %s, not a JPEG" % (len(body), st["type"]))
                body = None
            else:
                st["via"] = "http"
        except urllib.error.HTTPError as e:
            notes.append({401: "http: 401 — the login was refused",
                          403: "http: 403 — this account cannot view that channel",
                          404: "http: 404 — this firmware serves snapshots at a different path"}.get(
                              e.code, "http: HTTP %s" % e.code))
        except Exception as e:
            notes.append("http: %s: %s" % (type(e).__name__, str(e)[:80]))
    if body is None and mode in ("auto", "rtsp"):
        try:
            body = _cctv_rtsp(cfg, ch)
            st["via"] = "rtsp"
        except Exception as e:
            notes.append(str(e)[:120] if str(e).startswith("rtsp") else "rtsp: %s" % str(e)[:110])
    if body is not None:
        st["ok"] = True
        st["bytes"] = len(body)
        if _cctv_cache.get("_method"):
            st["auth_method"] = _cctv_cache["_method"]
    else:
        st["reason"] = " · ".join(notes[:2]) or "no frame from this channel"
    if st["ok"]:
        _cctv_cache[ck] = (body, dict(st))
    return (body if st["ok"] else None), st


def cctv_state():
    cfg = cctv_cfg()
    chans = cfg.get("channels") or []
    if not chans and cfg.get("present") and not cfg.get("error"):
        chans = [{"name": "ch %d" % i, "no": i} for i in range(1, int(cfg.get("count", 4)) + 1)]
    tiles, imgs = [], {}
    for ch in chans[:16]:
        img, st = cctv_tile(ch, cfg)
        tiles.append(st)
        if img:
            imgs[st["no"]] = img
    if not cfg.get("present"):
        tiles = [{"name": "not configured", "ok": False,
                  "reason": "no cctv.json — write the NVR's IP + login into ~/hermes_sentry/cctv.json; "
                            "the desk will then show every channel here"}]
    return {"cfg": {"present": cfg.get("present", False), "error": cfg.get("error"),
                    "host": cfg.get("host"), "user": cfg.get("user"),
                    "has_password": bool(cfg.get("password")), "port": cfg.get("port")},
            "tiles": tiles, "imgs": imgs, "n_ok": sum(1 for t in tiles if t.get("ok")),
            "n_total": len(tiles), "discovery": (None if cfg.get("present") else cctv_discover()),
            "auth": str(cfg.get("auth") or "auto").lower(), "mode": str(cfg.get("mode") or "auto").lower(),
            "ffmpeg": bool(_cctv_ffmpeg())}



# ---------------- dashboard ----------------
HTML = r'''<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hermes Trade Radar</title><style>
body{background:#0b0f17;color:#d7e0ea;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:16px}
h1{font-size:20px;margin:0 0 4px} .sub{color:#7f8ea3;font-size:12px;margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-bottom:14px}
.card{background:#121a26;border:1px solid #1e2a3a;border-radius:10px;padding:12px}
.k{color:#7f8ea3;font-size:11px;text-transform:uppercase;letter-spacing:.06em}
.v{font-size:20px;font-weight:700;margin-top:2px}.up{color:#2ecc71}.down{color:#e74c3c}.flat{color:#f1c40f}
table{width:100%;border-collapse:collapse;font-size:12px}th{color:#7f8ea3;text-align:left;font-weight:600;padding:6px 8px;border-bottom:1px solid #1e2a3a}
td{padding:6px 8px;border-bottom:1px solid #151f2d}tr:hover{background:#16202e}
pre{background:#0e1520;border:1px solid #1e2a3a;border-radius:8px;padding:10px;font-size:11px;white-space:pre-wrap;max-height:220px;overflow:auto}
.badge{display:inline-block;padding:2px 10px;border-radius:99px;font-size:11px;font-weight:700}
.b-live{background:#123b25;color:#2ecc71}.b-dead{background:#3b1212;color:#e74c3c}.b-red{background:#3b2f12;color:#f1c40f}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}@media(max-width:800px){.cols{grid-template-columns:1fr}}
/* Phone. It is the same page, not a second dashboard: a copy would be a second thing to keep honest. */
@media(max-width:760px){body{padding:10px}h1{font-size:17px}.grid{grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:7px}
.card{padding:9px}.v{font-size:16px}table{font-size:12px}th,td{padding:5px 6px}
pre{max-height:150px;font-size:10px}h2{margin:11px 0 5px}}
#phone{font-size:12px}
body.cmp .desk{display:none}body.cmp table{font-size:11px}body.cmp pre{max-height:110px}
button{background:#16202e;color:#d7e0ea;border:1px solid #1e2a3a;border-radius:8px;padding:5px 10px;font-size:12px}
h2{font-size:14px;margin:14px 0 6px;color:#9fb2c8}
</style></head><body>
<h1>📡 Hermes Trade Radar</h1>
<div class="sub">24/7 sentry monitor · playbook v3.0 · auto-refresh 10s · <span id="kl"></span> KL · <span id="age"></span></div>
<div id="badges"></div>
<div class="card" id="phone" style="margin-bottom:12px"></div>
<div class="grid" id="cards"></div>
<h2>Positions</h2><table id="pos"><tr><th>Symbol</th><th>Dir</th><th>Vol</th><th>Open</th><th>Last</th><th>SL</th><th>TP</th><th>P/L</th></tr></table>
<h2>Graded record — win rate the sizer is actually reading</h2>
<table id="record"><tr><th>Book</th><th>Win rate</th><th>W / L / voids</th><th>Graded</th><th>Net R</th><th>Best skill (accuracy)</th></tr></table>
<h2>Working orders</h2><h2>Money — total trades, wins, losses and the profit or loss, leg by leg</h2>
<div id="moneynote" class="sub"></div>
<table id="money"><tr><th>Leg</th><th>Total trades</th><th>Wins</th><th>Losses</th><th>No close yet</th><th>Profit / Loss</th><th>Floating</th><th>Account</th></tr></table>
<table id="ord"><tr><th>Symbol</th><th>Type</th><th>Price</th><th>SL</th><th>TP</th><th>State</th></tr></table>
<h2>Forex — the playbook across every chart it reads</h2>
<div id="fxnote" class="sub"></div>
<table id="fx"><tr><th>Symbol</th><th>Theme</th><th>Decided today</th><th>Bid / Ask</th></tr></table>
<div class="cols"><div><h2>Sentry journal</h2><pre id="journal"></pre></div>
<div><h2>Alert queue</h2><pre id="outbox"></pre></div></div>
<h2>Delivery channels</h2><pre id="channels"></pre>
<script>
const P = new URLSearchParams(location.search);
window.__K = P.get('k') ? ('?k=' + P.get('k')) : '';   // same-origin, same token: the page's own refreshes
                                                       // must authenticate exactly like the first load
async function tick(){
  try{
    const d = await (await fetch('data.json' + (window.__K || ''))).json();
    document.getElementById('kl').textContent = d.kl||'';
    // "DOWN" here means "the radar could not read fresh state", not "you lost money". Age is measured
    // against the desk's own stamp, so a sleeping laptop is visible from the phone at a glance.
    try{
      const t = Date.parse((d.kl||'').replace(' ','T')+'+08:00');
      const age = Math.max(0, Math.round((Date.now()-t)/1000));
      const el = document.getElementById('age');
      el.textContent = (age < 90 ? 'fresh' : age < 900 ? 'STALE' : 'DOWN') + ' · ' + age + 's';
      el.style.color = age < 90 ? '#2ecc71' : (age < 900 ? '#f1c40f' : '#e74c3c');
    }catch(e){}
    document.getElementById('badges').innerHTML =
      '<span class="badge '+(d.sentry_alive?'b-live':'b-dead')+'">SENTRY '+(d.sentry_alive?'LIVE':'DOWN')+'</span> '+
      (d.red_window?'<span class="badge b-red">RED WINDOW — no new entries</span>':'');
    const pl = d.float_pl||0;    const mny = d.money||{};
    const usd = v => (v==null ? '—'
      : (v<0?'−$':'+$')+Math.abs(v).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}));

    document.getElementById('cards').innerHTML =
      card('Floating P/L', (pl>=0?'+':'')+pl+' USD', pl>0?'up':(pl<0?'down':'flat'))+
      card('Positions', (d.positions||[]).length)+
      card('Working orders', (d.orders||[]).length)+
      card('Equity base', '100,000 demo')+
      card('Win rate', ((d.record&&d.record.overall&&d.record.overall.win_rate!=null)
            ? (100*d.record.overall.win_rate).toFixed(1)+'%' : '—'),
           (d.record&&d.record.overall&&d.record.overall.win_rate>=0.5)?'up':'down')+
      card('Graded outcomes', (d.record&&d.record.overall?d.record.overall.graded:0)+' ('
            +((d.record&&d.record.overall)?(d.record.overall.decisive||0):0)+' decisive)')+
      card('Total trades', mny.totals&&mny.totals.trades!=null?mny.totals.trades
            +(mny.totals.graded!=null?' ('+mny.totals.graded+' graded, '+(mny.totals.ungraded||0)+' open)':'')
            :'—')+
      // counts only — the win-rate card above owns that ratio, for a wider population
      card('Wins / Losses', (mny.totals&&(mny.totals.wins!=null||mny.totals.losses!=null))
            ?((mny.totals.wins||0)+'W / '+(mny.totals.losses||0)+'L'
              +(mny.totals.scratch?' · '+mny.totals.scratch+' void':''))
            :'—',
           (mny.totals&&mny.totals.usd!=null)?(mny.totals.usd>0?'up':'down'):'')+
      card('Profit / Loss', usd(mny.totals&&mny.totals.usd)+(mny.totals&&mny.totals.floating
            ?' ('+usd(mny.totals.floating)+' open)':''),
           (mny.totals&&mny.totals.usd>0)?'up':((mny.totals&&mny.totals.usd<0)?'down':''))+      card('Alert delivery', d.channels&&!d.channels.gmail_cfg&&!d.channels.webhook
            ? 'LOCAL ONLY' : (d.channels&&d.channels.webhook?'webhook':'mail'),
           (d.channels&&(d.channels.gmail_cfg||d.channels.webhook))?'up':'flat')+
      card('Alerts queued', d.channels?(d.channels.queued+'/'+(d.channels.cap||200)):'-',
           (d.channels&&d.channels.full)?'flat':'')+
      card('Urgent held', d.channels?(d.channels.urgent_held+' held, '+(d.channels.dropped||0)+' dropped')
            :'-', (d.channels&&d.channels.dropped)?'flat':'up');
    const a = d.access||{};
    const fw = a.firewall||{};
    document.getElementById('phone').innerHTML =
      '<span class="k">Phone / LAN</span><div class="v" style="font-size:14px;word-break:break-all">'
      + (a.phone_url ? '<a href="'+a.phone_url+'" style="color:#2ecc71">'+a.phone_url+'</a>'
                     : 'no LAN address right now (WiFi off?) — localhost still works')
      + '</div><div style="color:#7f8ea3;margin-top:4px">'
      + (fw.probed ? (fw.enabled ? 'macOS firewall <b>ON</b> — if the phone cannot load it, allow /usr/bin/python3 in Firewall, or use Tailscale' : 'macOS firewall off') : 'firewall state unknown')
      + (a.tailscale_ip ? ' · Tailscale <b>'+a.tailscale_ip.ip+':'+a.port+'</b> '
        + (a.tailscale_ip.up ? '(up — works away from home)' : '(configured but stopped: sudo tailscaled && tailscale up)') : '')
      + ' · localhost needs no token, anything else does ('+(a.token_len||0)+' chars)</div>'
      + ' <button id="cmpb">compact</button>'
      + (a.lan_ip ? ' <button id="cpb">copy link</button>' : '') + '</div>';
    const rec = d.record||{};
    const rrows = [];
    if(rec.fx) rrows.push(['forex (MT5)', rec.fx]);
    Object.entries(rec.books||{}).forEach(([k,v])=>rrows.push([k, v]));
    document.getElementById('record').innerHTML =
      '<tr><th>Book</th><th>Win rate</th><th>W / L / voids</th><th>Graded</th><th>Net R</th><th>Best skill (accuracy)</th></tr>'+
      rrows.map(([k,g])=>`<tr><td>${k}</td><td class="${g.win_rate>=0.5?'up':'down'}">${
        g.win_rate==null?'—':(100*g.win_rate).toFixed(1)+'%'}</td><td>${g.wins||0} / ${g.losses||0} / ${g.scratch||0}</td><td>${g.graded||0}</td><td>${g.net_r||0}</td><td>${
        (g.by_skill&&g.by_skill.length)?g.by_skill[0].skill+' '+(100*g.by_skill[0].acc).toFixed(0)+'% ('+g.by_skill[0].n+')':'—'}</td></tr>`).join('')
      + (rec.error?`<tr><td colspan="6">${rec.error}</td></tr>`:'');
    const cp = document.getElementById('cpb');    const mlegs = (d.money&&d.money.legs)||[];
    document.getElementById('money').innerHTML =
      '<tr><th>Leg</th><th>Total trades</th><th>Wins</th><th>Losses</th><th>No close yet</th>'
      +'<th>Profit / Loss</th><th>Floating</th><th>Account</th></tr>'
      + mlegs.map(x=>`<tr><td>${x.leg}${x.shadow?' <span class="sub">shadow · simulated fills</span>':''}</td>`
        +`<td>${x.trades==null?'—':x.trades}${x.trades_is=='graded'?' <span class="sub">graded</span>':''}</td>`
        +`<td class="up">${x.wins==null?'—':x.wins}</td><td class="down">${x.losses==null?'—':x.losses}</td>`
        +`<td>${x.ungraded==null?'—':x.ungraded}</td>`
        +`<td class="${x.usd>0?'up':(x.usd<0?'down':'')}">${usd(x.usd)}${x.usd==null?'':' '+x.currency}</td>`
        +`<td class="${x.floating>0?'up':(x.floating<0?'down':'')}">${usd(x.floating)}</td>`
        +`<td class="sub">${x.kind||'?'}${x.login?' '+x.login:''}${x.server?' @ '+x.server:''}`
        +`${x.asof?' · '+x.asof:''}</td></tr>`).join('')
      + ((d.money&&d.money.totals)?`<tr style="border-top:2px solid #243040"><td><b>every leg</b></td>`
        +`<td><b>${d.money.totals.trades==null?'—':d.money.totals.trades}</b></td>`
        +`<td class="up"><b>${d.money.totals.wins==null?'—':d.money.totals.wins}</b></td>`
        +`<td class="down"><b>${d.money.totals.losses==null?'—':d.money.totals.losses}</b></td>`
        +`<td><b>${d.money.totals.ungraded==null?'—':d.money.totals.ungraded}</b></td>`
        +`<td><b>${d.money.totals.net_r==null?'—':(d.money.totals.net_r>=0?'+':'')+d.money.totals.net_r.toFixed(2)}</b></td>`
        +`<td class="${d.money.totals.usd>0?'up':'down'}"><b>${usd(d.money.totals.usd)} ${d.money.totals.currency||''}</b></td>`
        +`<td><b>${usd(d.money.totals.floating)}</b></td>`
        +`<td class="sub">real leg ${usd(d.money.totals.real_usd)} · shadow ${usd(d.money.totals.shadow_usd)}</td></tr>`:'')
      + ((d.money&&d.money.totals&&d.money.totals.what)
        ?'<tr><td colspan="8" class="sub">'+d.money.totals.what+'</td></tr>':'')
      + (mlegs.length?'':'<tr><td colspan="8" class="sub">no leg published a ledger this cycle — '
        + 'an empty table means nothing was readable, NOT that nothing happened</td></tr>');
    document.getElementById('moneynote').textContent =
      ((d.money&&d.money.today&&d.money.today.graded!=null)
        ? ('today · '+(d.money.today.day||'?')+': '+d.money.today.graded+' graded ('+d.money.today.wins+'W/'
           +d.money.today.losses+'L, '+(d.money.today.ungraded||0)+' sent but no close yet) for '
           + usd(d.money.today.usd)
           +(d.money.today.usd_n!=null&&d.money.today.usd_n!==d.money.today.graded
              ?' (only '+d.money.today.usd_n+' of '+d.money.today.graded+' rows carry a $ figure)' : '')+' · ')
        : 'today · the ledger could not be read, so no day figure is claimed · ')
      + ((d.money&&d.money.totals&&d.money.totals.note) ? d.money.totals.note : '')
      + ((d.money&&d.money.kind) ? '  [account kind the terminal reports: '+d.money.kind+']' : '');

    if (cp) cp.onclick = function(){ const u = (a.phone_url||'');
      if (navigator.clipboard) navigator.clipboard.writeText(u); cp.textContent = 'copied'; };
    const cb = document.getElementById('cmpb'); if (cb) cb.onclick = function(){ document.body.classList.toggle('cmp'); };
    tbl('pos', d.positions||[], p=>`<tr><td>${p.sym}</td><td>${p.action}</td><td>${p.vol}</td><td>${p.open}</td><td>${p.last}</td><td>${p.sl}</td><td>${p.tp}</td><td class="${p.profit>0?'up':(p.profit<0?'down':'')}">${p.profit}</td></tr>`);
    tbl('ord', d.orders||[], o=>`<tr><td>${o.sym}</td><td>${o.type}</td><td>${o.price}</td><td>${o.sl}</td><td>${o.tp}</td><td>${o.state}</td></tr>`);
    // The chart matrix is the resident's OWN record of what it read last cycle, taken from state.json. The
    // page never asks the terminal, so a closed MetaTrader cannot make this table lie — it goes stale instead.
    const fx = d.fx_charts||{};
    const fxt = document.getElementById('fx');
    const fxn = document.getElementById('fxnote');
    const tfs = fx.tfs||[];
    // the header is built from the build's own timeframe list, so a column can never sit over the wrong cell
    const head = '<tr><th>Symbol</th><th>Theme</th>'+tfs.map(t=>'<th>'+t+'</th>').join('')
               +'<th>Decided today</th><th>Bid / Ask</th></tr>';
    if(!fx.published){
      fxt.innerHTML = '<tr><th>Symbol</th><th>Charts (bars · signals)</th><th>Decided</th><th>Quote</th></tr>'
        +'<tr><td colspan="4" style="color:#f1c40f">the resident on this Mac does not publish its per-chart '
        +'record yet — deploy the sentry_mac.py that writes <code>charts</code> into state.json and this table '
        +'fills in on its next cycle. Left empty on purpose: a blank table would read as "the playbook found '
        +'nothing on any chart", which is a different claim from "I have not been told".</td></tr>';
      fxn.textContent = '';
    } else {
      fxt.innerHTML = head + (fx.rows||[]).map(r=>{
        const cells = tfs.map(t=>{
          const c = (r.tf||{})[t]||{};
          if(c.bars==null) return '<td style="color:#7f8ea3">—</td>';
          const bar = c.bars+'/'+((fx.need||{})[t]||'?');
          return c.enough
            ? '<td>'+bar+' <span class="up">·</span> '+(c.pat||0)+'</td>'
            : '<td style="color:#f1c40f">'+bar+' not scanned</td>';
        }).join('');
        return '<tr><td><b>'+r.sym+'</b></td><td style="color:#7f8ea3">'+(r.theme||'—')+'</td>'+cells
          +'<td>'+(r.held?'<b style="color:#2ecc71">●'+r.held+'</b> ':'')+(r.fired||0)+(r.fired_rolling!=null
              ?' <span style="color:#7f8ea3">/'+r.fired_rolling+'</span>':'')+'</td>'
          +'<td>'+(r.bid!=null?(r.bid+' / '+(r.ask!=null?r.ask:'—'))
                   :'<span style="color:#f1c40f">no quote</span>')+'</td></tr>';
      }).join('');
      const rl = fx.rules||{};
      const band = rl.risk_band||[];
      fxn.innerHTML = 'as the resident recorded it: <b>'+(fx.asof||'—')+'</b>'
        +(fx.age_min!=null?' · state file '+fx.age_min+' min old':'')
        +(fx.stale?' <b style="color:#f1c40f">STALE — the build is not writing</b>':'')
        +(fx.positions_open!=null?' · '+fx.positions_open+' open forex position(s) in its own read':'')
        +(fx.book_n!=null?' · book it read: '+fx.book_n+' item(s)':'')
        +((fx.thin&&fx.thin.length)?' · <span style="color:#f1c40f">too few bars to scan: '+fx.thin.join(', ')+'</span>':'')
        +(fx.account_line?'<br>'+fx.account_line:'')
        +(fx.guard_line?'<br><span style="color:#7f8ea3">sizing floor:</span> '+fx.guard_line:'')
        +(fx.live_line?'<br><b>live record</b> · '+fx.live_line:'')
        +(fx.error?' · <b style="color:#e74c3c">its watch block raised: '+fx.error+'</b>':'')
        +'<br>rules as the build publishes them: cycle '+rl.cycle_s+'s · $'+(rl.risk_base||'?')+' self-scaled '
        +'inside $'+(band[0]||'?')+'–$'+(band[1]||'?')+' · max '+(rl.max_orders_day||'?')+'/day · '
        +(rl.orders||'')+' · '+(rl.red_window||'')
        +'<br><i>today/rolling</i> is the build\'s once-a-day key count for that symbol on '+(fx.day||'its day')
        +' — it stamps that key for a below-gate candidate, a refused entry AND a sent order alike, so it '
        +'counts DECISIONS, not orders; the rolling number spans several days. '
        +' over what is left in its rolling list (which spans several days, so it is NOT a per-day figure)'
        +(fx.held&&Object.keys(fx.held).length?' · holding '+Object.entries(fx.held).map(([k,v])=>k+'×'+v).join(', '):'')
        +'. <br>each cell is <i>bars / bars needed</i> then the patterns it has logged for that chart (a rolling '
        +'300-key list, cumulative — not a per-day hit rate). <span style="color:#f1c40f">not scanned</span> '
        +'means the checklist could not run, which says nothing about the market.';
    }
    document.getElementById('journal').textContent = d.journal_tail||'(empty)';
    document.getElementById('outbox').textContent = d.outbox_tail||'(queue empty)';
    document.getElementById('channels').textContent = d.channels
      ? ('gmail app-password file: '+(d.channels.gmail_cfg?'present':'MISSING — nothing leaves this Mac')+
         '\nnotifier binary: '+(d.channels.notifier?'present':'missing')+
         '\nlocal webhook: '+(d.channels.webhook||'not set (export HERMES_ALERT_WEBHOOK in the launchd plist to enable)')+
         '\nqueued / delivered: '+d.channels.queued+' / '+d.channels.sent+
         '\n\nNo Arena session is involved anywhere: alerts queue on disk and the radar drains them by itself.')
      : '(no channel report)';
  }catch(e){ document.getElementById('badges').innerHTML='<span class="badge b-dead">RADAR REFRESH ERROR</span>'; }
}
function card(k,v,cls){return `<div class="card"><div class="k">${k}</div><div class="v ${cls||''}">${v}</div></div>`;}
function tbl(id,rows,fn){const t=document.getElementById(id);t.innerHTML=t.rows[0].outerHTML+rows.map(fn).join('');}
tick(); setInterval(tick, 10000);
</script></body></html>'''

EMBED = '''<!DOCTYPE html><html><body style="margin:0;background:#0b0f17;color:#d7e0ea;font:12px -apple-system,sans-serif;padding:8px">
<b style="color:#2ecc71">● HERMES SENTRY</b> <span id="s">loading…</span>
<script>async function t(){try{const d=await(await fetch('data.json'+(location.search||''))).json();
document.getElementById('s').textContent='float '+(d.float_pl||0)+' USD · '+(d.positions||[]).length+' pos · '+(d.orders||[]).length+' orders · '+((d.money&&d.money.totals)?('trades '+(d.money.totals.trades==null?'—':d.money.totals.trades)+' · '+(d.money.totals.wins||0)+'W/'+(d.money.totals.losses||0)+'L · '+((d.money.totals.usd==null)?'—':((d.money.totals.usd<0?'-$':'+$')+Math.abs(d.money.totals.usd).toFixed(2))+' '+d.money.totals.currency+' · '):'')+((d.record&&d.record.overall&&d.record.overall.line)||'win rate —')+' · sentry '+(d.sentry_alive?'LIVE':'DOWN');}catch(e){}}
t();setInterval(t,15000);</script></body></html>'''



CCTV_HTML = r"""<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hermes CCTV</title><style>
body{background:#0b0f17;color:#d7e0ea;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:14px}
h1{font-size:18px;margin:0 0 4px}.sub{color:#7f8ea3;font-size:12px;margin-bottom:12px}
a{color:#2ecc71}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:10px}
@media(max-width:760px){.grid{grid-template-columns:1fr 1fr;gap:7px}body{padding:9px}h1{font-size:16px}}
.cam{background:#121a26;border:1px solid #1e2a3a;border-radius:10px;overflow:hidden}
.cam h3{margin:0;padding:7px 9px;font-size:12px;font-weight:600;color:#9fb2c8;display:flex;justify-content:space-between}
.cam .bd{position:relative;min-height:150px;background:#0e1520;display:flex;align-items:center;justify-content:center}
.cam img{width:100%;display:block;image-rendering:auto}
.err{padding:16px 12px;color:#e74c3c;font-size:12px;white-space:pre-wrap;text-align:left}
.warn{color:#f1c40f}
.k{color:#7f8ea3;font-size:11px;text-transform:uppercase;letter-spacing:.06em}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11px;font-weight:700}
.p-ok{background:#123b25;color:#2ecc71}.p-bad{background:#3b1212;color:#e74c3c}.p-wait{background:#3b2f12;color:#f1c40f}
.note{background:#101826;border:1px solid #1e2a3a;border-radius:10px;padding:12px;margin:12px 0;font-size:13px}
code{background:#0e1520;border-radius:4px;padding:1px 5px;font-size:12px}
button{background:#16202e;color:#d7e0ea;border:1px solid #1e2a3a;border-radius:8px;padding:5px 10px;font-size:12px}
</style></head><body>
<h1>🎥 CCTV — all channels</h1>
<div class="sub">same desk, same server, same token · <span id="age"></span> ·
  <button onclick="go()">refresh</button> <a href="./">← trading radar</a></div>
<div id="hdr"></div>
<div class="grid" id="grid"></div>
<div id="foot"></div>
<script>
const P = new URLSearchParams(location.search);
window.__K = P.get('k') ? ('?k=' + P.get('k')) : '';
        // ^ the tiles are separate requests from the page: the <img> tags and the cctv.json poll have to
        // carry the same token the page was opened with, or a phone that passed the gate once still gets
        // 403 on every frame and the grid stays empty. (Caught by rendering the page headlessly, not by
        // reading it.)
let TTL = 0;
function esc(x){ return String(x==null?'':x).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
                       // a camera's own text (its HTTP reason phrase, a name typed into cctv.json) lands in
                       // the page, so nothing from the wire goes in unescaped
function go(){
  fetch('cctv.json' + (window.__K || ''), {cache:'no-store'}).then(r=>r.json()).then(d=>{
    TTL = Math.floor(Date.now()/1000);   // cache-buster: a fixed value would let a phone keep showing the
                                         // frame it fetched first, which is how a dead camera looks alive
    const t = d.tiles||[];
    document.getElementById('grid').innerHTML = t.map((c,i)=>
      `<div class="cam"><h3><span>${esc(c.name)||('ch '+(c.no||i+1))}</span>`
      + (c.ok ? '<span class="pill p-ok">LIVE '+(c.via||'')+(c.auth_method?'·'+c.auth_method:'')+'</span>' : (c.needs_auth ? '<span class="pill p-wait">LOGIN</span>'
                                                                       : '<span class="pill p-bad">DOWN</span>'))
      + `</h3><div class="bd">`
      + (c.ok ? `<img alt="" src="cctv.jpg?ch=${c.no}${(window.__K?'&'+window.__K.slice(1):'')}&x=${TTL}"
                 style="cursor:zoom-in" onclick="this.dataset.big=!this.dataset.big;this.style.width=this.dataset.big==='true'?'100%':''">`
              : `<div class="err ${c.needs_auth?'warn':''}">${esc(c.reason||'no image')}</div>`)
      + `</div></div>`).join('') || '<div class="note">no channels listed</div>';
    const cfg = d.cfg||{};
    document.getElementById('hdr').innerHTML =
      `<div class="note">${cfg.present ? ('configured: <code>'+(cfg.host||'?')+'</code>'
        + (cfg.user?(' user <code>'+cfg.user+'</code>'):' <b class="warn">no user/password yet</b>')
        + ` · ${d.n_ok||0}/${d.n_total||0} channels answering`)
        : 'CCTV is not wired yet.' + (d.cfg && d.cfg.error ? ' '+d.cfg.error : '')}
      ${!cfg.present ? `<div style="margin-top:8px">Create <code>~/hermes_sentry/cctv.json</code> (mode 600):
        <pre style="max-height:none">{ "host": "${((d.discovery&&d.discovery.found&&d.discovery.found[0])||{}).ip||'192.168.0.x'}",
  "user": "admin", "password": "the NVR password", "count": 8,
  "auth": "auto", "mode": "auto", "subtype": 1,   // auth: auto|digest|basic|privkey|none · mode: auto|http|rtsp
  "channels": [ {"name":"Front gate","no":1}, {"name":"Car park","no":2} ] }</pre>
        The password never leaves this Mac: the tiles below are proxied by the desk, so no browser —
        yours or a stranger's on the WiFi — ever sees it.</div>` : ''}
      ${(d.discovery&&d.discovery.found&&d.discovery.found.length)
        ? '<div style="margin-top:6px;color:#7f8ea3">found on the LAN: '
          + d.discovery.found.map(f=>`<code>${f.ip}:${f.port}</code> (${f.what}${f.model?` — <b>${esc(f.brand)} ${esc(f.model)}</b> · ONVIF ${f.onvif?'yes':'no'}`:''})`).join(', ') + '</div>' : ''}</div>`;
    const blocked = t.filter(x=>x.needs_auth);
    const why = blocked.length ? (blocked[0].anon||{}) : null;
    if (why && (why.code||why.note)) {
      document.getElementById('hdr').innerHTML += '<div class="note" style="margin-top:8px;border-color:#3b2f12">'
        + '<b class="warn">Why this page asks for a login.</b> The desk asked the recorder for a frame with '
        + 'no credentials at all, and <i>the recorder</i> answered: <code>'
        + esc(why.code) + (why.challenge ? ' ' + esc(why.challenge) : '') + '</code> on <code>'
        + esc(why.url) + '</code>. Every anonymous path is closed — RTSP answers 401 too, and ONVIF media '
        + 'needs a token — so there is no trick left to find: this box will not hand live video to an '
        + 'unauthenticated client, which is the correct behaviour for a camera on an office LAN. '
        + 'Two ways to make the page work with no typing on your side: create a view-only user in the XVR '
        + '(Menu &rarr; Account, type Normal User, no admin rights) and put that pair in cctv.json — or turn '
        + 'on guest/anonymous view on the box and set <code>"auth": "none"</code>, and the desk will use it '
        + 'the next refresh. '
        + (why.open ? '<b class="p-ok">It already answers without a login — just set "auth": "none".</b>' : '')
        + '</div>';
    }
    document.getElementById('foot').innerHTML =
      '<div class="sub" style="margin-top:14px">Thumbnails are pulled every 20 s by the desk, not streamed '
      + 'by the phone, so this page costs almost no battery or bandwidth. Tap a tile to enlarge it. '
      + 'The NVR itself refuses to be embedded in another page (it sends <code>X-Frame-Options: SAMEORIGIN</code>), '
      + 'which is why this is a proxy and not an iframe.</div>';
    try{ const el=document.getElementById('age'); el.textContent='updated '+new Date().toLocaleTimeString(); }catch(e){}
    TTL++;
  }).catch(()=>{ const el=document.getElementById('age'); if(el) el.textContent='desk unreachable'; });
}
go(); setInterval(go, 20000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body.encode())
    def _denied(self):
        self.send_response(403)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        try:
            self.wfile.write(("<!doctype html><meta charset=utf-8><body style=\"background:#0b0f17;"
                              "color:#d7e0ea;font:15px -apple-system,sans-serif;padding:24px\">"
                              "<b>Open the address from the desk page or the radar log — it carries ?k=…</b>"
                              "<p style=\"color:#7f8ea3\">This page shows positions and P/L, so anything that"
                              " is not this Mac has to present the token. (http://127.0.0.1:8790 on the Mac"
                              " itself needs nothing.)</body>").encode())
        except Exception:
            pass

    def do_GET(self):
        # Local loopback stays effortless — the Mac's own browser and the embed. Everything else, including
        # his phone on the same WiFi, must carry the token. The path is checked as a whole segment ("/../"
        # is refused) because this server only ever serves three fixed routes.
        client = (self.client_address[0] if self.client_address else "") or ""
        path = self.path.split("?")[0]
        if path not in ("/", "/index.html", "/data.json", "/embed", "/cctv", "/cctv.json", "/cctv.jpg"):
            self.send_error(404)
            return
        if not is_local(client):
            qs = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            if qs.get("k", [""])[0] != security_key():
                return self._denied()      # exact compare, and an absent token lands here too
        if path.startswith("/data.json"):
            self._send(json.dumps(snapshot()), "application/json")
        elif path.startswith("/cctv.json"):
            st = cctv_state()
            st.pop("imgs", None)
            st["updated"] = time.strftime("%H:%M:%S")
            self._send(json.dumps(st), "application/json")
        elif path.startswith("/cctv.jpg"):
            # Proxied so the NVR password stays on the Mac. One tile per image is a design choice, not a
            # shortcut: an <img> tag cannot send an Authorization header, and putting the login in the src
            # URL would leak it into the phone's history and into any proxy between them.
            qs = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            want = (qs.get("ch") or ["1"])[0]
            body = None
            for ch, img in (cctv_state().get("imgs") or {}).items():
                if str(ch) == str(want):
                    body = img
                    break
            if not body:
                self.send_error(503)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except Exception:
                pass                                  # a phone that hangs up mid-jpeg must not kill the desk
        elif path.startswith("/cctv"):
            self._send(CCTV_HTML, "text/html")
        elif path.startswith("/embed"):
            self._send(EMBED, "text/html")
        else:
            self._send(HTML, "text/html")

if __name__ == "__main__":
    threading.Thread(target=digest_loop, daemon=True).start()
    print(f"Trade Radar on 0.0.0.0:{PORT}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
