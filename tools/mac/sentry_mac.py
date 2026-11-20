#!/usr/bin/env python3
"""Trade Sentry — always-on checklist evaluator + executor (demo account).

Loop (every CYCLE seconds):
  1. Pull quotes + M15/H1 candles + open book via the Mac MCP bridge (mac_connect.sh).
  2. Compute indicators: EMA20/50, RSI(14), ATR(14), Bollinger(20,2)  [playbook §5].
  3. Evaluate mechanical skill checklists S1/S2/S4 [playbook §4].
  4. On hit -> caps gate -> dry-check -> place PENDING order -> journal (4-question block).
  5. Housekeeping: +1R breakeven moves, equity day-window deletion, red-window bans.

Guardrails ENFORCED: pending orders only, score >= 4, one per symbol-skill per day, no duplicate within 1.5xATR
of a placed order, broker min-lot + measured margin floor + the equity risk cap, and a pre-send geometry check.
ADVISORY ONLY (journalled, never enforced): the $600 theme cap and MAX_SENTRY_ORDERS_DAY. v4.8.0 spells the
difference out because v4.7.9's header advertised "<=4/day" as a guardrail while fire() wrote a NOTE and kept
sending — 22 entries on 2026-11-20, 46 on 11-17.
"""
import json, math, os, re, subprocess, sys, time
from datetime import datetime, timedelta

CYCLE = 300            # seconds between scans
RISK = 100.0           # $ baseline per entry — Sentry self-scales actual size via self_size()
MIN_RISK, MAX_RISK = 50.0, 200.0     # bounds on self-sizing (v3.1)
MAX_SENTRY_ORDERS_DAY = 4
# v4.7.9: how much of the account ONE minimum-size position may risk. On a $50 base the broker's 0.01-lot
# floor risks ~$3.70 on a EURUSD stop and ~$34 on a gold stop, so the floor - not the strategy - decides
# the risk. Where even the floor is over this fraction of equity the trade is refused, loudly. Override per
# desk with "risk_max_frac_of_equity" in desk_mode.json (0 turns the guard off).
MAX_RISK_FRAC = 0.10
THEME_CAP = {"dollar": 600.0, "equity": 600.0, "crypto": 600.0}   # soft caps, counted from LIVE book

# The five charts the playbook reads, and how many closed bars each needs before the symbol is scanned at all.
# These used to be five numbers hard-coded inside the scan loop, which meant nothing else could tell "no signal
# on M15" apart from "M15 is not there yet" — the difference between a quiet market and a dead feed. They live
# here so the scan and the desk page read THE SAME bar minimums, and the page can print the shortfall.
TF_MIN = {"M5": 25, "M15": 15, "H1": 60, "H4": 30, "D1": 8}
TFS = ["M5", "M15", "H1", "H4", "D1"]

# ---- Broker-agnostic symbol universe (v3.1): names/specs resolved from the terminal catalog ----
BASE_THEME = {"XAUUSD": "dollar", "EURUSD": "dollar", "GBPUSD": "dollar", "NVDA": "equity", "AMD": "equity"}
# top-10 crypto by market cap in preference order; first MAX_CRYPTO the broker actually lists get traded
CRYPTO_BASES = [("BTC", "BTCUSD|BTCUSDT|XBTUSD"), ("ETH", "ETHUSD|ETHUSDT"), ("XRP", "XRPUSD|XRPUSDT"),
                ("SOL", "SOLUSD|SOLUSDT"), ("BNB", "BNBUSD"), ("DOGE", "DOGEUSD"), ("ADA", "ADAUSD"),
                ("TRX", "TRXUSD"), ("LTC", "LTCUSD"), ("BCH", "BCHUSD"), ("LINK", "LINKUSD"),
                ("AVAX", "AVAXUSD"), ("DOT", "DOTUSD")]
MAX_CRYPTO = 10
MULT, THEME, DIGITS, VSPEC = {}, {}, {}, {}      # sym -> contract $/unit, theme, digits, (vmin, vstep, vmax)
MARGIN = {}          # sym -> margin the broker requires for ONE minimum-size position
FX, CRYPTO_SET, EQUITY_SET, SYMS = set(), set(), set(), []

# Fallback used when catalog discovery is unavailable (classic Arena Trader set)
FALLBACK = {"XAUUSD": (100.0, 2, "dollar", (0.01, 0.01, 100.0)),
            "EURUSD": (100000.0, 5, "dollar", (0.01, 0.01, 100.0)),
            "GBPUSD": (100000.0, 5, "dollar", (0.01, 0.01, 100.0)),
            "NVDA": (1.0, 2, "equity", (1.0, 1.0, 1000000.0)),
            "AMD": (1.0, 2, "equity", (1.0, 1.0, 1000000.0))}
def use_fallback():
    for s, (mult, dig, th, vs) in FALLBACK.items():
        MULT[s], DIGITS[s], THEME[s], VSPEC[s] = mult, dig, th, vs
        if th == "dollar" and s != "XAUUSD": FX.add(s)
        if th == "equity": EQUITY_SET.add(s)
    SYMS[:] = list(FALLBACK)
def book_theme_risk(pos_text):
    """Parse live book -> {theme: committed $ risk}. None on parse failure."""
    try:
        m = re.search(r'"text": "(.*)"\s*}\s*]', pos_text, re.S)
        if not m: return None
        data = json.loads(m.group(1).encode().decode("unicode_escape"))
        orders = data[0] if isinstance(data, list) and data else []
        posses = data[1] if isinstance(data, list) and len(data) > 1 else []
        used = {}
        for o in orders:
            sym = o.get("symbol"); th = THEME.get(sym)
            if not th: continue
            try:
                risk = float(o.get("volume_initial") or o.get("volume_current") or 0) * MULT.get(sym, 0.0) * abs(float(o.get("stop_loss") or 0) - float(o.get("price_order") or 0))
                used[th] = used.get(th, 0.0) + risk
            except Exception: pass
        for p in posses:
            sym = p.get("symbol"); th = THEME.get(sym)
            if not th: continue
            try:
                risk = float(p.get("volume") or 0) * MULT.get(sym, 0.0) * abs(float(p.get("stop_loss") or 0) - float(p.get("price_open") or 0))
                used[th] = used.get(th, 0.0) + risk
            except Exception: pass
        return used
    except Exception:
        return None

STATE_F = "/Users/sakib/hermes_sentry/state.json"
JOURNAL_F = "/Users/sakib/hermes_sentry/sentry_journal.md"
MAC = None  # native on the Mac: bash -c directly

TL_PATH = __file__.rsplit("/", 1)[0] + "/trades_log.jsonl"
REVIEW_PATH = __file__.rsplit("/", 1)[0] + "/REVIEW.md"
def tl_log(rec):
    try:
        rec["ts"] = kl_now().strftime("%Y-%m-%d %H:%M")
        with open(TL_PATH, "a") as f: f.write(json.dumps(rec) + "\n")
    except Exception: pass
def tl_update_rid(rid, result):
    try:
        rows = [json.loads(x) for x in open(TL_PATH) if x.strip()]
        for row in reversed(rows):
            if row.get("rid") == rid and "result" not in row:
                row["result"] = result; row["R"] = 1.0 if result == "win" else -1.0; break
        with open(TL_PATH, "w") as f:
            for row in rows: f.write(json.dumps(row) + "\n")
    except Exception: pass
def tl_update_close(sym, profit):
    try:
        rows = [json.loads(x) for x in open(TL_PATH) if x.strip()]
        for row in reversed(rows):
            if row.get("sym") == sym and row.get("fired") and "result" not in row:
                row["result"] = "win" if profit > 0 else "loss"
                row["profit"] = profit
                row["R"] = round(profit / float(row.get("risk") or 100), 2); break
        with open(TL_PATH, "w") as f:
            for row in rows: f.write(json.dumps(row) + "\n")
    except Exception: pass
def daily_review():
    try:
        try:
            rows = [json.loads(x) for x in open(TL_PATH) if x.strip()]
        except FileNotFoundError:
            rows = []
        def rate(sel):
            w = len([r for r in sel if r.get("result") == "win"]); n = len(sel)
            return f"{w}W-{n-w}L" if n else "no data"
        live = [r for r in rows if r.get("fired") and r.get("result")]
        paper = [r for r in rows if not r.get("fired") and r.get("result")]
        lines = [f"# SENTRY REVIEW — {kl_now().strftime('%Y-%m-%d %H:%M')} KL\n",
                 f"LIVE record: {rate(live)} | skipped-candidates (paper): {rate(paper)}\n\n",
                 "| skill | source | W-L | avg R | n |\n|---|---|---|---|---|\n"]
        by = {}
        for r in live + paper:
            by.setdefault((r.get("skill"), "LIVE" if r.get("fired") else "paper"), []).append(r)
        for (sk, src), rs in sorted(by.items()):
            w = len([r for r in rs if r.get("result") == "win"]); n = len(rs)
            rr = [r.get("R") for r in rs if isinstance(r.get("R"), (int, float))]
            lines.append(f"| {sk} | {src} | {w}W-{n-w}L | {sum(rr)/len(rr):+.2f}R | {n} |\n")
        open(REVIEW_PATH, "w").writelines(lines)
        journal_alert("DAILY REVIEW — " + rate(live) + " live · " + rate(paper) + " paper. Table in REVIEW.md; tune weights with the brain.")
    except Exception as e:
        journal(f"review error: {e}")

def kl_now():
    return datetime.utcnow() + timedelta(hours=8)

# ---- v3.1: runtime symbol discovery (broker-agnostic, suffix-tolerant) ----
DISCOVER = r'''
U="http://127.0.0.1:22346/mcp"
K="$(iconv -f UTF-16LE -t UTF-8 "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/config/assistant.ini" 2>/dev/null | tr -d "\r" | grep -m1 -o "ApiKey=[A-Za-z0-9]*" | cut -d= -f2)"
curl -sS --compressed -D /tmp/sn_dh -o /dev/null --max-time 30 -X POST "$U" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Authorization: Bearer $K" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-06-18\",\"capabilities\":{},\"clientInfo\":{\"name\":\"sentry\",\"version\":\"1.0\"}}}"
SID=$(grep -iE "^mcp-session-id:" /tmp/sn_dh | tr -d "\r" | awk "{print \$2}")
curl -sS --compressed -o /dev/null -X POST "$U" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Mcp-Session-Id: $SID" -H "Authorization: Bearer $K" -d "{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}"
curl -sS --compressed -o /tmp/sn_dc -X POST "$U" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Mcp-Session-Id: $SID" -H "Authorization: Bearer $K" -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"get_marketwatch_symbols\",\"arguments\":{\"include_hidden\":true,\"limit\":50000}}}"
python3 - << 'EPY'
import json
env = None
raw = open("/tmp/sn_dc").read()
try:
    env = json.loads(raw)
except Exception:
    for line in raw.splitlines():
        if line.startswith("data:"):
            try: env = json.loads(line[5:].strip())
            except Exception: pass
try:
    data = json.loads(env["result"]["content"][0]["text"])
    for s in data.get("symbols", []):
        print("RES " + json.dumps({
            "sym": str(s.get("symbol", "")), "desc": str(s.get("description", ""))[:40],
            "digits": s.get("digits", 2), "cs": s.get("contract_size", 1),
            "vmin": s.get("volume_min", 0.01), "vstep": s.get("volume_step", 0.01),
            "vmax": s.get("volume_max", 1e6)}))
except Exception as e:
    print("DISCOVER_ERR %s" % e)
EPY
'''

def discover_symbols():
    """Resolve base names against the broker catalog: exact or short-suffixed (e.g. EURUSDm).
    Crypto: first MAX_CRYPTO top-10 tickers the broker actually lists, any suffix."""
    raw = mac(DISCOVER)
    cat = {}
    bad = 0
    for line in raw.splitlines():
        if not line.startswith("RES "): continue
        try:
            r = json.loads(line[4:])
            cat[r["sym"]] = {"desc": r["desc"], "digits": int(float(r["digits"])), "cs": float(r["cs"]),
                            "vmin": float(r["vmin"]), "vstep": float(r["vstep"]), "vmax": float(r["vmax"])}
        except Exception:
            bad += 1
    if bad: journal(f"symbol discovery: {bad} malformed catalog rows skipped")
    if not cat:
        journal(f"symbol discovery failed (no catalog; raw {len(raw)} chars) — keeping current universe")
        return False
    newM, newT, newD, newV = {}, {}, {}, {}
    newFX, newCRY, newEQ, order = set(), set(), set(), []
    def add(sym, th):
        c = cat[sym]
        newM[sym], newD[sym], newT[sym] = c["cs"], c["digits"], th
        newV[sym] = (c["vmin"], c["vstep"], c["vmax"])
        order.append(sym)
    for base, th in BASE_THEME.items():
        pat = re.compile(re.escape(base) + r"(?:[._\-]?[A-Za-z0-9]{1,3})?$")
        hits = sorted([s for s in cat if pat.fullmatch(s)], key=len)
        if not hits and base in ("NVDA", "AMD"):
            kw = "nvidia" if base == "NVDA" else "advanced micro"
            hits = sorted([s for s, c in cat.items() if kw in c["desc"].lower()], key=len)
        if not hits: continue
        add(hits[0], th)
        if th == "dollar" and not hits[0].startswith("XAU"): newFX.add(hits[0])
        if th == "equity": newEQ.add(hits[0])
    found = 0
    for name, pat in CRYPTO_BASES:
        if found >= MAX_CRYPTO: break
        rx = re.compile("(?:" + pat + r")(?:[._\-]?[A-Za-z0-9]{1,3})?$")
        hits = sorted([s for s in cat if rx.fullmatch(s)], key=lambda x: (len(x), x))
        if not hits: continue
        add(hits[0], "crypto"); newCRY.add(hits[0]); found += 1
    if not order:
        journal("symbol discovery: no usable symbols in catalog — keeping current universe")
        return False
    if found == 0:
        journal("crypto discovery: broker lists no top-10 coins — forex/equity only this account")
    MULT.clear(); MULT.update(newM); THEME.clear(); THEME.update(newT)
    DIGITS.clear(); DIGITS.update(newD); VSPEC.clear(); VSPEC.update(newV)
    FX.clear(); FX.update(newFX); CRYPTO_SET.clear(); CRYPTO_SET.update(newCRY)
    EQUITY_SET.clear(); EQUITY_SET.update(newEQ); SYMS[:] = order
    journal(f"symbol discovery: {len(order)} live · crypto {sorted(newCRY) if newCRY else 'NONE'} · equity {sorted(newEQ) if newEQ else 'NONE'}")
    return True

# ---- v3.1: self-sizing — Sentry decides its own risk from its recent accuracy ----
def skill_acc(skill, rows=None):
    """Win rate (0..1) of the trades we ACTUALLY SENT and the terminal ACTUALLY closed.

    v4.7.9 scanned the last 120 LINES of the ledger and counted any row with a result, weighting live trades 2x
    and rejected candidates 1x. Measured on the running account 2026-11-20: of those last 120 rows, 61 carried
    a result and ZERO of them were sent trades — so the figure driving position size was made of bar-touch
    outcomes for signals the gate had already refused, and because only 7 of 39 graded skills had >=3 rows in
    that window, 32 fell through to the global average: S4-band-fade-long, C-M15-marubozu and S18-ma-revert-long
    (three unrelated skills) all read exactly 0.615. Fired + terminal-graded only now. A skill with fewer than 3
    such trades still blends toward the LIVE global, so cold hands stay neutral without inheriting the paper book.
    """
    try:
        rows = tl_rows() if rows is None else rows
    except Exception:
        return 0.5
    w = n = gw = gn = 0.0
    for r in rows:
        if not r.get("fired") or r.get("result") not in ("win", "loss", "scratch"): continue
        if r.get("grade_source") != "terminal": continue
        win = 1.0 if r["result"] == "win" else 0.0
        gn += 1.0; gw += win
        if r.get("skill") == skill:
            n += 1.0; w += win
    if n >= 3: return w / n
    if gn > 0: return (w + gw) / (n + gn) if (n + gn) > 0 else 0.5
    return 0.5

def self_size(skill, score):
    """risk = base * (0.5 + accuracy) * score-bump — hot hands size up, cold hands size down."""
    a = skill_acc(skill)
    risk = RISK * (0.5 + a) * (1.0 + 0.25 * (score - 4))
    return max(MIN_RISK, min(MAX_RISK, round(risk)))


def red_window():
    """No new entries 20:15-22:30 KL (US red-data window incl. CPI/PPI/NFP 20:30)."""
    t = kl_now().hour * 60 + kl_now().minute
    return 20 * 60 + 15 <= t <= 22 * 60 + 30

def equity_window_open():
    """US regular session in KL terms: 21:30-04:30 KL."""
    t = kl_now().hour * 60 + kl_now().minute
    return t >= 21 * 60 + 30 or t <= 4 * 60 + 30

def load_state():
    try:
        with open(STATE_F) as f: s = json.load(f)
    except Exception:
        s = {}
    s.setdefault("day", kl_now().strftime("%Y-%m-%d"))
    if s["day"] != kl_now().strftime("%Y-%m-%d"):
        s.update({"day": kl_now().strftime("%Y-%m-%d"), "orders": [], "theme_risk": {}, "logs": []})
    s.setdefault("orders", []); s.setdefault("theme_risk", {}); s.setdefault("logs", [])
    return s


def publish_watch(state, quotes, tf_map, positions, chart_thin=None, book_raw=""):
    """Write down, for the desk page, what is OPEN and what the five charts look like this cycle.

    Read-only in the sense that matters: it parses text this cycle already fetched and adds fields that no
    decision reads. If a scan is ever late or wrong, the fix is never in this function — the guardrails are
    upstream of it and this only reports. Two details are the reason the numbers can be trusted:

      * `r_now` is R multiples LIVED, from the position's own stop distance, so +1.4R means +1.4R whether the
        symbol is gold or a tech stock. A span of zero (stop sitting on entry, which the terminal does allow
        mid-modify) returns None instead of dividing by it;
      * each chart row carries `enough` against TF_MIN rather than a bare bar count, so "0 patterns" on a
        chart with 12 bars reads as NOT SCANNED, not as "the playbook found nothing here".
    """
    now = time.time()
    poss = parse_positions(positions or "")
    for p in poss:
        d = 1.0 if str(p["action"]).lower().startswith("buy") else -1.0
        span = abs(p["open"] - p["sl"])     # a DISTANCE, so a short's favourable move reads +R, not -R
        p["r_now"] = round((p["last"] - p["open"]) * d / span, 3) if span else None
        try:
            _ts = str(p["time"]).strip().replace("T", " ").replace("Z", "")[:19]
            p["age_min"] = max(0, int((now - datetime.strptime(_ts, "%Y-%m-%d %H:%M:%S").timestamp()) / 60))
        except Exception:
            p["age_min"] = None
    state["positions_now"] = poss[:40]
    state["positions_total_pl"] = round(sum(p["profit"] for p in poss), 2)
    state["positions_open"] = len(poss)
    state["orders_now"] = list(state.get("orders") or [])[:20]
    book = []
    for m in re.finditer(r'"order_id": "(\d+)".*?"symbol": "([A-Za-z0-9._\-]+)".*?"type": "([\w ]+)".*?'
                         r'"state": "(\w+)".*?"price_order": ([0-9.]+)', book_raw or "", re.S):
        book.append({"ticket": m.group(1), "sym": m.group(2), "type": m.group(3).strip(),
                     "state": m.group(4), "price": float(m.group(5))})
    state["book"] = {"n": len(book), "items": book[:40]}
    seen = list(state.get("seen_candles") or [])
    fired = list(state.get("fired_today") or [])
    day = str(state.get("day") or "")        # the build's own KL day, which is what it stamps keys with
    # The universe is quotes + charts + whatever the book currently holds. A symbol can lose its charts
    # (broker rename, catalog hiccup) while a trade on it is still open, and a page keyed off quotes alone
    # would stop showing that trade's chart — the one row worth seeing.
    charts = {}
    _uni = list(quotes or {}) + list(tf_map or {}) + [p.get("sym") for p in poss] \
           + [b.get("sym") for b in book]
    universe = sorted(set(x for x in _uni if x))
    for sym in universe:
        tf = (tf_map or {}).get(sym, {})
        row = {}
        for t in TFS:
            bars = tf.get(t) or []
            row[t] = {"bars": len(bars), "last": (bars[-1].get("t") if bars else None),
                      "patterns": sum(1 for k in seen if k.startswith("%s|%s|" % (sym, t))),
                      "enough": len(bars) >= TF_MIN[t]}
        # keys are "FIRE|SYM|SKILL|YYYY-MM-DD", so [1] is the symbol and [3] the day the build stamped.
        row["fired_today"] = sum(1 for k in fired if len(k.split("|")) > 3 and k.split("|")[1] == sym
                                 and k.split("|")[3] == day)
        row["fired_rolling"] = sum(1 for k in fired if len(k.split("|")) > 1 and k.split("|")[1] == sym)
        row["fired_days"] = sorted({k.split("|")[3] for k in fired if len(k.split("|")) > 3 and k.split("|")[1] == sym})
        row["theme"] = THEME.get(sym) or BASE_THEME.get(sym) or "?"
        row["quote"] = (quotes or {}).get(sym) or {}
        # exposure as the build sees it, counted here so both pages quote the same figure instead of each
        # deriving it from a different list (the desk used to count positions, the radar counted orders).
        row["held"] = sum(1 for p in poss if p.get("sym") == sym)
        row["resting"] = sum(1 for b in book if b.get("sym") == sym)
        if (chart_thin or {}).get(sym):
            row["thin"] = chart_thin[sym]
        charts[sym] = row
    state["charts"] = charts
    state["charts_thin"] = dict(chart_thin or {})
    state["playbook"] = {"cycle_s": CYCLE, "risk_base": RISK, "risk_band": [MIN_RISK, MAX_RISK],
                         "max_orders_day": MAX_SENTRY_ORDERS_DAY, "theme_cap": THEME_CAP,
                         "timeframes": TFS, "bars_needed": TF_MIN,
                         "orders": "pending only (limit/stop) — never market",
                         "red_window": "no new entries 20:15-22:30 KL (crypto exempt)",
                         "candle_library": "H1 + M15 closed bars; one entry per pattern-per-bar",
                         "universe": {x: THEME.get(x, BASE_THEME.get(x, "?")) for x in (SYMS or [])}}
    state["watch_asof"] = kl_now().strftime("%Y-%m-%d %H:%M:%S KL")
    state.pop("watch_error", None)

def save_state(s):
    with open(STATE_F, "w") as f: json.dump(s, f)

def journal(line):
    stamp = kl_now().strftime("%m-%d %H:%M KL")
    with open(JOURNAL_F, "a") as f: f.write(f"- **{stamp}** {line}\n")
    print(f"[{stamp}] {line}", flush=True)

_last_wake = [0.0]

def alert(msg):
    try:
        with open(os.path.dirname(STATE_F) + "/alerts.outbox", "a") as f:
            f.write(f"{kl_now().strftime('%m-%d %H:%M KL')} | {msg}\n")
    except Exception:
        pass
    # No wake-wire, by request (2026-11-17): the desk used to POST urgent lines into an Arena session so an
    # agent could react live, which made continuity depend on a browser being logged in. The outbox above is
    # the record; the radar on :8790 turns it into a notification, a mail or a local webhook, and an event
    # nobody sees still survives in the journal and on the page. Nothing here wakes a session.
    urgent = msg.startswith(("FILL", "CANDIDATE", "CHECK/SEND FAILED"))
    if not urgent and time.time() - _last_wake[0] < 180:
        return
    _last_wake[0] = time.time()
    url = os.environ.get("HERMES_ALERT_WEBHOOK", "").strip()
    if url.startswith("http"):
        try:
            import urllib.request
            body = json.dumps({"text": msg[:700]}).encode()
            urllib.request.urlopen(urllib.request.Request(
                url, data=body, headers={"Content-Type": "application/json"}, timeout=4), timeout=5).read()
        except Exception:
            pass

def journal_alert(msg):
    journal(msg); alert(msg)

def mac(cmd, timeout=120):
    """Local shell, on this Mac — not a bridge: no session, no remote agent, nothing to feed.

    It reaches MetaTrader 5 through the terminal's OWN local MCP endpoint (127.0.0.1:22346), a MetaQuotes
    feature alive exactly as long as the terminal is. So the order path survives with every chat/wake job
    disabled: continuity comes from launchd + the terminal, not from an agent being awake.
    """
    try:
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except Exception as e:
        journal(f"local exec error: {e}")
        return ""

FETCH = r'''
U="http://127.0.0.1:22346/mcp"
K="$(iconv -f UTF-16LE -t UTF-8 "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/config/assistant.ini" 2>/dev/null | tr -d "\r" | grep -m1 -o "ApiKey=[A-Za-z0-9]*" | cut -d= -f2)"
BODY="{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-06-18\",\"capabilities\":{},\"clientInfo\":{\"name\":\"sentry\",\"version\":\"1.0\"}}}"
curl -sS --compressed -D /tmp/sn_hi -o /dev/null --max-time 30 -X POST "$U" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Authorization: Bearer $K" -d "$BODY"
SID=$(grep -iE "^mcp-session-id:" /tmp/sn_hi | tr -d "\r" | awk "{print \$2}")
curl -sS --compressed -o /dev/null -X POST "$U" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Mcp-Session-Id: $SID" -H "Authorization: Bearer $K" -d "{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}"
CALL(){ : > "$1"; curl -sS --compressed -o "$1" -X POST "$U" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Mcp-Session-Id: $SID" -H "Authorization: Bearer $K" -d "$2"; }
if [ -n "$SID" ]; then echo "@@BRIDGE up"; else echo "@@BRIDGE down"; fi
echo "@@QUOTES"
CALL /tmp/sn_mw "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"get_marketwatch_symbols\",\"arguments\":{}}}"
sed "s/^data: *//" /tmp/sn_mw | tr -d "\\" > /tmp/sn_mwc
for S in __LIST__; do
grep -o "{ *\"selected\"[^}]*\"symbol\": \"$S\"[^}]*}" /tmp/sn_mwc | head -1 | grep -o "\"bid\": *[0-9.]*\|\"ask\": *[0-9.]*" | tr "\n" " " | sed "s/^/$S /"
echo ""
done
for S in __LIST__; do
for T in M5 M15 H1 H4 D1; do
echo "@@B $T $S"
CALL /tmp/sn_b "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"get_chart_history\",\"arguments\":{\"symbol\":\"$S\",\"period\":\"$T\",\"datetime_from\":\"__FROM__\",\"datetime_to\":\"__TO__\",\"limit\":120}}}"
sed "s/^data: *//" /tmp/sn_b | tr -d "\\" | grep -o "{ *\"time\"[^}]*}" | sed "s/{ *\"time\": //;s/\"tick_volume.*//" | tail -60
done
done
echo "@@POSITIONS"
CALL /tmp/sn_op "{\"jsonrpc\":\"2.0\",\"id\":5,\"method\":\"tools/call\",\"params\":{\"name\":\"get_trading_open_positions\",\"arguments\":{}}}"
sed "s/^data: *//" /tmp/sn_op | tr -d "\\"
echo "@@ACCOUNT"
CALL /tmp/sn_ac "{\"jsonrpc\":\"2.0\",\"id\":6,\"method\":\"tools/call\",\"params\":{\"name\":\"get_trading_account_info\",\"arguments\":{}}}"
sed "s/^data: *//" /tmp/sn_ac | tr -d "\\"
__EXTRA__
'''

FETCH_HIST = r'''
echo "@@HISTORY"
CALL /tmp/sn_hp "{\"jsonrpc\":\"2.0\",\"id\":7,\"method\":\"tools/call\",\"params\":{\"name\":\"get_trading_history_positions\",\"arguments\":{}}}"
sed "s/^data: *//" /tmp/sn_hp | tr -d "\\"
'''

def build_fetch(need_hist=False):
    """FETCH with the live symbol universe + a rolling 30-day candle window.

    The close history is the biggest blob this bridge carries, and it is worth asking for only while a sent
    trade is still waiting for its outcome - so the caller says whether this cycle needs it.
    """
    frm = (kl_now() - timedelta(days=30)).strftime("%Y-%m-%dT00:00:00")
    to = (kl_now() + timedelta(days=1)).strftime("%Y-%m-%dT23:59:00")
    extra = FETCH_HIST if need_hist else ""
    return (FETCH.replace("__LIST__", " ".join(SYMS)).replace("__FROM__", frm).replace("__TO__", to)
            .replace("__EXTRA__", extra))

def parse_bars(block):
    bars = []
    for m in re.finditer(r'"([^"]+)", "open": ([0-9.]+), "high": ([0-9.]+), "low": ([0-9.]+), "close": ([0-9.]+)', block):
        bars.append({"t": m.group(1), "o": float(m.group(2)), "h": float(m.group(3)),
                     "l": float(m.group(4)), "c": float(m.group(5))})
    return bars

def parse_quotes(block):
    q = {}
    for line in block.splitlines():
        m = re.match(r'(\S+) "bid": ([0-9.]+) "ask": ([0-9.]+)', line.strip())
        if m: q[m.group(1)] = {"bid": float(m.group(2)), "ask": float(m.group(3))}
    return q

def parse_positions(raw):
    pos = []
    for m in re.finditer(r'"position_id": "(\d+)".*?"action": "(\w+)".*?"symbol": "([A-Za-z0-9._\-]+)".*?"create_time": "([^"]+)".*?"volume": ([0-9.]+), "price_open": ([0-9.]+), "price_last": ([0-9.]+), "stop_loss": ([0-9.]+), "take_profit": ([0-9.]+), "profit": (-?[0-9.]+)', raw, re.S):
        pos.append({"id": m.group(1), "action": m.group(2), "sym": m.group(3), "time": m.group(4),
                    "vol": float(m.group(5)), "open": float(m.group(6)), "last": float(m.group(7)),
                    "sl": float(m.group(8)), "tp": float(m.group(9)), "profit": float(m.group(10))})
    return pos

def mcp_call(tool, args_json):
    payload = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                          "params": {"name": tool, "arguments": json.loads(args_json)}}).replace("'", "'\\''")
    script = r'''
K="$(iconv -f UTF-16LE -t UTF-8 "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/config/assistant.ini" 2>/dev/null | tr -d "\r" | grep -m1 -o "ApiKey=[A-Za-z0-9]*" | cut -d= -f2)"
curl -sS --compressed -D /tmp/sn_hi -o /dev/null --max-time 30 -X POST "http://127.0.0.1:22346/mcp" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Authorization: Bearer $K" -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-06-18\",\"capabilities\":{},\"clientInfo\":{\"name\":\"sentry\",\"version\":\"1.0\"}}}"
SID=$(grep -iE "^mcp-session-id:" /tmp/sn_hi | tr -d "\r" | awk "{print \$2}")
curl -sS --compressed -o /dev/null -X POST "http://127.0.0.1:22346/mcp" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Mcp-Session-Id: $SID" -H "Authorization: Bearer $K" -d "{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}"
curl -sS --compressed -o /tmp/sn_cx -X POST "http://127.0.0.1:22346/mcp" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Mcp-Session-Id: $SID" -H "Authorization: Bearer $K" -d '__PAYLOAD__'
sed "s/^data: *//" /tmp/sn_cx | head -c 300
'''.replace("__PAYLOAD__", payload)
    return mac(script)

def ema(vals, n):
    k = 2.0 / (n + 1); out = [sum(vals[:n]) / n]
    for v in vals[n:]: out.append(v * k + out[-1] * (1 - k))
    return out

def rsi(closes, n=14):
    if len(closes) < n + 2: return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n; al = (al * (n - 1) + losses[i]) / n
    if al == 0: return 100.0
    return 100 - 100 / (1 + ag / al)

def atr(h1, n=14):
    if len(h1) < n + 2: return 0.0
    trs = []
    for i in range(1, len(h1)):
        trs.append(max(h1[i]["h"] - h1[i]["l"], abs(h1[i]["h"] - h1[i-1]["c"]), abs(h1[i]["l"] - h1[i-1]["c"])))
    a = sum(trs[:n]) / n
    for t in trs[n:]: a = (a * (n - 1) + t) / n
    return a

def bollinger(closes, n=20, k=2.0):
    if len(closes) < n: return None
    w = closes[-n:]; m = sum(w) / n
    sd = (sum((x - m) ** 2 for x in w) / n) ** 0.5
    return m - k * sd, m, m + k * sd

def pivots(h1, back=2):
    hi, lo = [], []
    for i in range(back, len(h1) - back):
        seg = h1[i - back: i + back + 1]
        if h1[i]["h"] == max(s["h"] for s in seg): hi.append(h1[i]["h"])
        if h1[i]["l"] == min(s["l"] for s in seg): lo.append(h1[i]["l"])
    return hi, lo

def trend(hi, lo):
    if len(hi) < 3 or len(lo) < 3: return "none"
    if hi[-1] < hi[-2] < hi[-3] and lo[-1] < lo[-2] < lo[-3]: return "down"
    if hi[-1] > hi[-2] > hi[-3] and lo[-1] > lo[-2] > lo[-3]: return "up"
    return "none"

def rnd(sym, x): return round(x, DIGITS[sym])

def fmt_px(sym, v):
    """One price, one shape, everywhere the terminal is asked to believe it.

    A price carrying more decimals than the symbol has digits is not 'loosely rounded' — MT5
    refuses it outright with retcode 10015 Invalid price, and it refuses the CHECK call, before an
    order exists, so the candidate simply evaporates.  Candidate levels come out of arithmetic
    (pivot * factor, last - 2*ATR) and keep every binary float digit: 1.3165645839210065, not
    1.31656.  The journal printed them through rnd(), so the desk read a clean 1.31656 while the
    terminal had been handed 1.3165645839210065 — the log and the order disagreed, which is why
    this took a payload test to see.  It was NOT the cause of the refusals: a digit-clean sell stop
    above the market is refused just the same.  See pending_geom for what actually was.

    Every number this build submits as a price goes through here, so what the desk journals and
    what the desk sends are the same number.  Volumes never pass through it — formatting, not
    sizing.  Falls back to 5 digits for a symbol the catalog has not described yet, and hands
    back anything it cannot read as a number untouched (a None TP is the senders problem, as
    before, not one this function invents a price for).
    """
    try:
        return '%.*f' % (int(DIGITS.get(sym, 5)), float(v))
    except Exception:
        return v

# --- pending-order geometry: which side of the market the terminal insists the entry sits on. ---
# Found the hard way, while answering "sentry down?": 90 journal lines read
# "CHECK/SEND FAILED ... retcode 10015 Invalid price", which looks like a price-format problem and is
# mostly NOT one.  Probed against the live terminal, three calls differing only in type/price:
#     sell stop  0.26 GBPUSD at 1.31256 (below the market)  ->  ok, retcode 0 Done
#     sell limit 0.26 GBPUSD at 1.31656 (above the market) ->  ok, retcode 0 Done
#     sell stop  0.26 GBPUSD at 1.31656 (ABOVE the market) ->  retcode 10015 Invalid price
# A stop joins a move, so it must start on the far side of the price from the trade it opens; a limit
# waits for a pullback and must start on the near side.  Candidates here are computed from
# CLOSED-candle structure, so between the scan and the terminal the market can cross the level, and
# the order then describes something the book does not accept.  The build used to learn that from a
# broker error code, retry the same frozen level every cycle (entry #37 at 23:22 and again at 23:39),
# and say nothing about it.  Now it says so here, in words, before spending the call.
#
# Deliberately NOT done: re-pricing the entry, or flipping stop<->limit.  A sell stop that has become
# a sell limit is a different trade — a breakdown entry versus a fade of the rally — and this build
# does not invent trades it was not signalled.  So a crossed level simply does not get sent, which is
# exactly what happens today anyway, plus a reason and a counter.
GEOM = {"buy stop": "above", "sell stop": "below", "buy limit": "below", "sell limit": "above"}


def pending_geom(sym, otype, entry, sl, tp, bid, ask):
    """(ok, reason).  Says nothing when it cannot see the market: a missing or unparseable quote must
    never become the reason a signalled trade was not sent — that way lies a silent strategy."""
    side = GEOM.get(otype)
    if side is None:                       # market order, or a type this build does not use
        return True, ""
    try:
        entry = float(entry); sl = float(sl or 0); tp = float(tp or 0)
        bid = float(bid); ask = float(ask)
    except (TypeError, ValueError):
        return True, ""
    if bid <= 0 or ask <= 0 or entry <= 0:
        return True, ""
    e = fmt_px(sym, entry); s_ = fmt_px(sym, sl) if sl else "0"
    if side == "above" and entry <= ask:
        return False, ("%s at %s is not beyond the ask %s — the level has been crossed since it was "
                       "drawn; the terminal answers 10015 Invalid price" % (otype, e, fmt_px(sym, ask)))
    if side == "below" and entry >= bid:
        return False, ("%s at %s is not beyond the bid %s — the level has been crossed since it was "
                       "drawn; the terminal answers 10015 Invalid price" % (otype, e, fmt_px(sym, bid)))
    long_ = otype.startswith("buy")
    if sl and ((sl >= entry) if long_ else (sl <= entry)):
        return False, ("stop-loss %s is on the wrong side of the %s entry %s"
                       % (s_, otype, e))
    if tp and ((tp <= entry) if long_ else (tp >= entry)):
        return False, ("take-profit %s is on the wrong side of the %s entry %s"
                       % (fmt_px(sym, tp), otype, e))
    return True, ""


def sz(sym, stop_dist, risk=None):
    """Size from risk alone, with no knowledge of the account.

    SUPERSEDED on the entry path by size_report() (v4.7.9), which reads the terminal's equity and journalls
    what the broker's minimum lot makes impossible instead of returning 0 in silence. Kept because it is the
    rule that applies when there is no account information at all, and because the Mac-side test imports it.
    Do not route a NEW send through this — an order too small for the broker disappears here without a trace.
    """
    risk = RISK if risk is None else risk
    if stop_dist <= 0: return 0
    v = risk / (stop_dist * MULT.get(sym, 1.0))
    vmin, vstep, vmax = VSPEC.get(sym, (0.01, 0.01, 1000000.0))
    if vstep > 0: v = math.floor(v / vstep + 1e-9) * vstep
    v = round(v, 6)
    return v if vmin <= v <= vmax else 0

SEND_ID_KEYS = ("order", "order_id", "order_ticket", "retcode_order", "deal", "deal_id", "ticket", "position_id")
SEND_OK_RETCODE = 10009        # TRADE_RETCODE_DONE — the terminal took the request

def _one_line(s, n=170):
    return re.sub(r"\s+", " ", (s or "").strip())[-n:]

def parse_send_result(out):
    """Read the terminal's answer to a send: its retcode, its words, and the order number if it named one.

    The reply is an MCP text blob with escaped JSON inside, and the field carrying the new order's id has
    moved between builds, so every alias is tried before concluding there is none. An accepted send with no
    id still counts as accepted (retcode 10009) — the trade is real, only the join key is missing — and it
    says so out loud instead of journalling a bare '?', which is how six days of fills went unattributed.
    """
    t = out or ""
    d = {"retcode": None, "details": None, "ticket": None, "ticket_key": None, "ok": False,
         "rejected": False, "keys": [], "raw": _one_line(t)}
    # both shapes occur: the reply is JSON inside JSON, so an inner quote may or may not still be escaped
    for bad in ('"ok": false', r'"ok\": false', "not permitted", r'isError\":true', 'isError":true'):
        if bad in t:
            d["rejected"] = True
            break
    m = re.search(r'\\?"retcode\\?"\s*:\s*(\d{4,6})', t)
    if m: d["retcode"] = int(m.group(1))
    m = re.search(r'\\?"(?:retcode_details|retcode_text|error|message)\\?"\s*:\s*\\?"([^"\\]{2,80})', t)
    if m: d["details"] = m.group(1)
    for k in SEND_ID_KEYS:
        m = re.search(r'\\?"%s\\?"\s*:\s*\\?"?(\d{5,})' % k, t)
        if m:
            d["ticket"], d["ticket_key"] = m.group(1), k
            break
    d["keys"] = sorted(set(re.findall(r'\\?"([a-z_]{3,20})\\?"\s*:', t)))[:24]
    # A reply can be a bare retcode with no "ok" field anywhere — that is the shape the SEND call
    # answers with ("retcode": 10015, "retcode_details": "Invalid price").  Read literally that is
    # neither accepted nor refused, and this parser said so: rejected stayed False, so send_order fell
    # past the refusal branch and the reply was only ever explained by the fallthrough line.  No live
    # trade is lost either way (ok was already False, so nothing was recorded as sent) — this is about
    # the word "rejected" meaning what it says, because that is the flag the CHECK/SEND FAILED line, the
    # only refusal the desk can see, is keyed on.  Measured before writing it: SEND REFUSED appears 0
    # times in today's journal, CHECK/SEND FAILED 91 times; the 148 bare reply dumps are all 11-13,
    # from an "UNPARSED send result" line this build no longer has.  A ticket still wins, so a build
    # that answers a placed pending order with 10008 plus an id cannot be misread as a failure.
    if not d["rejected"] and d["retcode"] not in (None, 0, SEND_OK_RETCODE) and d["ticket"] is None:
        d["rejected"] = True
    d["ok"] = (not d["rejected"]) and (d["retcode"] == SEND_OK_RETCODE or d["ticket"] is not None)
    return d

# ---- v4.7.9: read the account, size against the broker's floor, and grade from the terminal's own closes ----
# Three separate blind spots are closed here, and they are related: the build could not see how big its own
# account was (so it could size a $50 balance like a $100k one), it could not tell "too small to trade" from
# "no signal" (a size below 0.01 lot returned 0 and nothing was journalled), and it could not tell whether a
# trade it sent ever became a position (mcp_call truncates its reply to 300 bytes, so the close history never
# parsed and 94 of 94 sent rows stayed ungraded). Each one is printed as what it is now.

def _fld(blk, key):
    """One scalar from a terminal record, quoted or bare. None rather than a guess."""
    m = re.search(r'"%s":\s*"([^"]*)"|"%s":\s*([-\w:.+ ]+?)(?=\s*[,}])' % (key, key), blk)
    if not m: return None
    v = m.group(1) if m.group(1) is not None else m.group(2).strip()
    return v or None

def _num(v):
    try: return float(v)
    except Exception: return None

def _account_record(raw):
    """The account object ALONE, not the whole reply.

    FETCH pipes the reply through `tr -d "\\"` to unescape the MCP text payload, and that is what turns the
    inner `\"type\": \"demo\"` into bare `type: demo` — but it also leaves the OUTERMCP envelope's own
    `{"type": "text"}` sitting in the same string, one field away. Reading the whole blob therefore returned
    "text" as this account's type (it did, on the first live cycle). The account object is the one that
    carries an equity, so scope every field read to it and the envelope cannot answer for it.
    """
    t = raw or ""
    # Prefer the key the server actually names the object with, then any figure we know belongs to it. If
    # neither is found the whole reply is returned and the field readers do their worst, rather than a slice
    # built from a guess.
    i = t.find("\"account\"")
    if i < 0:
        i = t.find("\"equity\"")
    if i < 0:
        i = t.find("\"balance\"")
    if i < 0:
        return t
    a = t.rfind("{", 0, i)
    b = t.find("}", i)
    return t[a:] if (a < 0 or b < 0) else t[a:b + 1]

def parse_account(raw):
    """The terminal's own account record: login, server, type, balance, equity, currency, margin mode.

    Keys come and go between terminal builds (and demo replies are known to drop fields real ones carry),
    so every field is optional and a missing equity means "no ceiling this cycle", never "unlimited".
    """
    blk = _account_record(raw)
    out = {}
    for k in ("login", "server", "broker", "type", "currency", "margin_mode", "name"):
        v = _fld(blk, k)
        if v is not None: out[k] = v
    for k in ("balance", "equity", "margin", "margin_free", "profit", "credit"):
        v = _num(_fld(blk, k))
        if v is not None: out[k] = v
    return out

def parse_closed(raw):
    """Closed positions the terminal reports, each with the comment the order was sent under."""
    out = []
    for blk in re.findall(r'\{\s*"position_id".*?\}', raw or "", re.S):
        tid = _fld(blk, "position_id"); sym = _fld(blk, "symbol")
        if not tid or not sym: continue
        row = {"ticket": str(tid), "sym": sym, "comment": _fld(blk, "comment") or "",
               "type": _fld(blk, "type"), "profit": _num(_fld(blk, "profit")),
               "open_time": _fld(blk, "open_time"), "close_time": _fld(blk, "close_time"),
               "open_price": _num(_fld(blk, "open_price")), "close_price": _num(_fld(blk, "close_price")),
               "stop_loss": _num(_fld(blk, "stop_loss")), "volume": _num(_fld(blk, "open_volume")),
               "contract_size": _num(_fld(blk, "contract_size")), "reason": _fld(blk, "close_reason")}
        out.append(row)
    return out

def comment_for(skill):
    """The comment send_order stamps on the wire. The terminal caps it at 31 chars, so matching must too —
    comparing the untruncated string would silently never match a long skill name."""
    return ("Sentry %s" % (skill or ""))[:31]

_STAMP_FMTS = (("%Y-%m-%d %H:%M:%S.%f", 26), ("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d %H:%M", 16),
               ("%Y-%m-%d", 10))

def _stamp(s):
    """Parse a timestamp from either side of the bridge. The log writes MINUTE precision
    ("%Y-%m-%d %H:%M") while the terminal writes SECONDS, so a single format silently returns None for every
    row in the log — and a None there used to mean "skip the time window", which let a close 47 days old be
    attributed to a brand-new trade. Both halves are fixed here: parse what each side really writes, and
    refuse to guess when the sent side still cannot be read."""
    t = str(s or "").strip().replace("T", " ").replace("Z", "").split("+")[0]
    for fmt, n in _STAMP_FMTS:
        try:
            return datetime.strptime(t[:n], fmt)
        except Exception:
            continue
    return None

KL_OFFSET_H = 8        # kl_now() is utcnow()+8h; the terminal stamps its own records in UTC

def match_closes(rows, closed, known_tickets=None, window_h=6, ticket_window_h=240):
    """Join our sent trades to the terminal's closed positions. Nothing invented, nothing double-counted.

    The key is the order comment — send_order stamps every request "Sentry <skill>", so a closed position
    names the skill that put it on. When the send response did carry an order number, that is used instead
    and it must agree. A closed position can settle only one row (the closest open_time to the send, inside
    window_h), because the same skill fires on the same symbol on different days. Rows the terminal has no
    close for stay ungraded on purpose: an open trade is not a result.
    """
    known = set(str(t) for t in (known_tickets or []) if t)
    # Only an ALREADY-GRADED row has consumed its close. Excluding the ticket of an ungraded row would rule
    # out the one close that belongs to it — which is exactly how this function first shipped, and the test
    # below is what it was caught by.
    used = {str(r.get("ticket")) for r in rows if r.get("ticket") and r.get("result")} | known
    pool = [c for c in (closed or []) if c.get("ticket") and c["ticket"] not in used]
    out = []
    for r in rows:
        if not r.get("fired") or r.get("result"): continue
        want = str(r.get("ticket") or "")
        sent = _stamp(r.get("ts"))
        best = None
        for c in pool:
            if c.get("sym") != r.get("sym"): continue
            if want:
                if c["ticket"] != want: continue
            elif (c.get("comment") or "") != comment_for(r.get("skill")): continue
            gap = 0.0
            # Two bounds, because the two keys are not equally strong. A COMMENT can only be trusted over a
            # short window: the same skill fires on the same symbol on other days, and without this bound a
            # close from 47 days ago settled a row sent this morning (a real bug the test below caught).
            # An exact TICKET needs no such tightness — a limit order rests for days before it fills, while
            # tl_log's ts is stamped at send time — so it gets its own, wider window.
            lim = ticket_window_h if want else window_h
            if not want and sent is None:
                continue                              # comment-only matching MUST be time-bounded
            if sent is not None and c.get("open_time"):
                ot = _stamp(c["open_time"])
                if ot is None: continue
                gap = abs((ot - (sent - timedelta(hours=KL_OFFSET_H))).total_seconds()) / 3600.0
                if gap > lim: continue
            if best is None or gap < best[0]: best = (gap, c)
        if not best: continue
        c = best[1]; pool.remove(c); used.add(c["ticket"])
        pf, risk = c.get("profit"), _num(r.get("risk"))
        out.append({"rid": r.get("rid"), "ticket": c["ticket"], "sym": r.get("sym"), "skill": r.get("skill"),
                    "profit": pf, "risk": risk, "open_time": c.get("open_time"), "close_time": c.get("close_time"),
                    "result": ("win" if (pf or 0) > 0 else "scratch" if (pf or 0) == 0 else "loss"),
                    "R": (round(pf / risk, 2) if pf is not None and risk else None),
                    "via": ("ticket" if want else "comment")})
    return out

def tl_grade_terminal(upd):
    """Write one terminal-confirmed outcome onto its sent row — real R, not the +/-1 the paper track uses."""
    try:
        rows = [json.loads(x) for x in open(TL_PATH, errors="replace") if x.strip()]
        for row in rows:
            if row.get("rid") == upd["rid"] and "result" not in row:
                row["result"] = upd["result"]
                if upd.get("profit") is not None: row["profit"] = upd["profit"]
                if upd.get("R") is not None: row["R"] = upd["R"]
                row["ticket"] = upd["ticket"]; row["grade_source"] = "terminal"
                break
        with open(TL_PATH, "w") as f:
            for row in rows: f.write(json.dumps(row) + "\n")
        return True
    except Exception:
        return False

def live_record(rows, ccy=None):
    """What we can say about the trades that were ACTUALLY SENT — kept apart from the paper track, because
    the paper track grades the candidates the gate rejected and uses a fixed +/-1R."""
    sent = [r for r in rows if r.get("fired")]
    g = [r for r in sent if r.get("result") in ("win", "loss", "scratch")]
    term = [r for r in g if r.get("grade_source") == "terminal"]
    rs = [r["R"] for r in g if isinstance(r.get("R"), (int, float))]
    return {"sent": len(sent), "graded": len(g), "from_terminal": len(term),
            "wins": sum(1 for r in g if r["result"] == "win"),
            "losses": sum(1 for r in g if r["result"] == "loss"),
            "scratch": sum(1 for r in g if r["result"] == "scratch"),
            "ungraded": len(sent) - len(g), "net_r": round(sum(rs), 2),
            "net_usd": round(sum(r.get("profit") or 0 for r in term), 2),
            "win_rate": (round(100.0 * sum(1 for r in g if r["result"] == "win") / len(g), 1) if g else None),
            # carried so a reader knows what the profit figure is DENOMINATED in: a demo account's USD is not
            # a wallet balance, and a cent- or non-USD account's numbers are not dollars at all.
            "currency": ccy or "USD"}

def tl_rows(limit=None):
    """Every row the ledger holds — the whole file unless a limit is asked for.

    v4.7.9 read `[-600:]` for BOTH the published record and the sizer's accuracy, and the ledger is mostly
    refused candidates, so graded trades aged out of what the build looks at while still sitting on disk.
    Measured 2026-11-20 on the running account: file 714 rows / 174 sent / 63 graded; the last 600 held
    137 sent / 36 graded — and 36 is what the desk published. Nine rows appended ten minutes later moved the
    published net P&L from $169.60 to $111.66 with no trade opened or closed. Reading a few hundred KB whole
    costs one parse per cycle; a record that quietly forgets itself costs the calibration of everything else.
    """
    try:
        rows = [json.loads(x) for x in open(TL_PATH, errors="replace") if x.strip()]
    except Exception:
        return []
    return rows[-limit:] if limit else rows

def has_ungraded_sent(rows=None):
    """True when a trade we sent is still waiting for its outcome — the only reason to pull the history."""
    return any(r.get("fired") and not r.get("result") for r in (rows if rows is not None else tl_rows()))

LIVE_FLOOR_FRAC = 0.01      # the per-trade ceiling a REAL account gets until the desk chooses another one
ACCT_KIND = ""              # the terminal's own account type, mirrored so the send path can see it


def note_account_kind(a):
    """Remember what kind of money the terminal says this is, module-wide.

    Two places need the answer and neither is allowed to guess: send_order, which must not put a real
    account's money to work on the strength of a file written for rehearsal, and risk_max_frac, which
    must not carry the demo's 10 % ceiling over a balance that can actually be overdrawn.  Anything that
    is not POSITIVELY a demo counts as real — including "unknown", because a build that could not read its
    own account is in no position to assume it is safe to trade.  That costs a cycle at startup, and it is
    the only direction this can be wrong in that does not cost money.
    """
    global ACCT_KIND
    ACCT_KIND = str((a or {}).get("type") or "").strip().lower()
    return ACCT_KIND


def account_is_real():
    # Lowercased HERE as well, not left to note_account_kind: "the only writer normalises it" is exactly
    # the kind of invariant that survives until someone sets the global from a new place, and the failure
    # this one makes is a real account being treated as safe.  A missed demo costs a cycle; the reverse
    # costs money.
    k = ACCT_KIND.lower()
    return not ("demo" in k or "trial" in k)


def risk_max_frac():
    """The equity ceiling on one minimum-size position, from the desk's own file. Missing/bad -> default;
    0 disables the guard, which is what the main $100k demo wants (its sizes are nowhere near the floor)."""
    try:
        cfg = json.load(open(os.path.dirname(STATE_F) + "/desk_mode.json"))
        v = cfg.get("risk_max_frac_of_equity")
        if v is not None:
            return max(0.0, float(v))        # the desk chose it: honoured, demo or not
    except Exception:
        pass
    # Nothing was chosen.  Then the account decides, and a real one does not inherit the demo's ceiling:
    # $100 on a $101k rehearsal is 0.1 %, the same $100 on a $1,000 live balance is the whole 10 % guard
    # firing every single trade.  1 % is where a live account starts, and it is one line to change.
    return LIVE_FLOOR_FRAC if account_is_real() else MAX_RISK_FRAC

def parse_margin(out, sym, ccy=None):
    """The margin the broker asked for the size we asked about, or None.

    It does NOT try to confirm the symbol: trade_order_calc_margin answers with the figure and its currency
    and does not echo the symbol back (proved against the live reply), and a check that can never pass is
    worse than no check — it reads as 'the broker refused' when it means 'we could not read'. What it does
    insist on: ok is true, the number is a number, and the currency is the account's own. A reply denominated
    in something else is refused as unknown rather than compared against a USD balance.
    """
    # Two transports, two shapes: FETCH pipes the bridge through tr -d of the backslash, mcp_call does not,
    # so the same field arrives escaped from one and clean from the other. Drop every backslash before
    # matching: no figure parsed below can contain one, and a regex that only fits the clean form returns
    # None -- which the caller would report as "the terminal would not answer", a true
    # statement about this parser and an unfair one about the terminal.
    t = (out or "")[:4000].replace(chr(92), "")
    t = re.sub(r"^data: *", "", t)
    if re.search(r'.?"ok".?.?:[^0-9]*(false|False|0)', t): return None

    m = re.search(r'"margin":\s*([0-9.]+)', t)
    if not m: return None
    c = re.search(r'"currency"\s*:\s*"([A-Za-z]{3})"', t)
    if ccy and c and c.group(1).upper() != str(ccy).upper(): return None
    v = float(m.group(1))
    return round(v, 4) if v > 0 else None

def measure_margin(sym, quotes, ccy=None):
    """Ask the broker what ONE minimum-size position costs in margin. Never guessed from leverage.

    Margin is a second floor and it is independent of the balance, so it is the only thing that can make a
    trade impossible on a small account while the R it risks looks tiny: one share of a $185 stock risks
    $2.50 to the stop and still cannot be posted on $50. Returns None when the terminal will not say, and
    the caller must then size without this check and say so -- absence of a number is not a licence.
    """
    vmin = VSPEC.get(sym, (0.01, 0.01, 1e6))[0]
    q = quotes.get(sym) if isinstance(quotes, dict) else None
    px = _num((q or {}).get("bid")) or _num((q or {}).get("ask")) or 0.0
    for price in (px, 0.0):
        if price <= 0: price = 1.0          # the terminal re-prices at market when it has no tick
        try:
            r = mcp_call("trade_order_calc_margin", json.dumps(
                {"symbol": sym, "type": "buy", "volume": vmin, "price": price}))
            m = parse_margin(r, sym, ccy)
            if m and m > 0: return round(m, 4)
        except Exception:
            continue
    return None

def size_report(sym, stop_dist, risk, equity=None, max_frac=None, margin=None, margin_frac=0.95):
    """Decide a volume the way the broker will, and say why when it cannot be done.

    verdicts: ok | round_up_to_min_lot (the intent is smaller than the floor, so the floor is traded and
    risk_actual says what that really risks) | min_lot_too_big (even the floor breaks the equity ceiling) |
    below_min_lot (floor allowed only when there is no equity to check against) | over_max_lot | no_stop.
    A missing equity never turns into an unlimited licence: the ceiling checks are simply skipped and
    `equity_known` says so, so the desk can print the gap instead of hiding it.
    """
    max_frac = risk_max_frac() if max_frac is None else float(max_frac)
    vmin, vstep, vmax = VSPEC.get(sym, (0.01, 0.01, 1000000.0))
    mult = MULT.get(sym, 1.0)
    risk = _num(risk) or 0.0
    out = {"sym": sym, "risk_asked": round(risk, 2), "risk": round(risk, 2), "capped": False,
           "stop_dist": stop_dist, "vmin": vmin, "vstep": vstep,
           "vmax": vmax, "contract": mult, "lots_wanted": 0.0, "lots": 0.0, "min_lot_risk": None,
           "risk_actual": None, "frac_of_equity": None, "equity": equity, "max_frac": max_frac, "margin": margin, "margin_frac": margin_frac,
           "equity_known": bool(equity and equity > 0), "verdict": "ok", "why": ""}
    stop_dist = _num(stop_dist)
    if not stop_dist or stop_dist <= 0 or not mult:
        out.update(verdict="no_stop", why="no stop distance to size against, so nothing can be sized")
        return out
    per_lot = stop_dist * mult
    out["min_lot_risk"] = round(vmin * per_lot, 2)
    # The margin floor FIRST, because it is not a risk question: a $185 notional cannot be posted on $50
    # however small its stop is. Measured, never derived -- leverage is not even published by account_info.
    if margin and isinstance(equity, (int, float)) and equity > 0 and margin > margin_frac * float(equity):
        out.update(lots=0.0, verdict="min_margin_too_big",
                   why="the broker needs $%.2f of margin for one %s unit and the account holds $%.2f, so "                       % (float(margin), vmin, float(equity))
                       + "the trade cannot be opened at any risk size (equity is not free margin: other "                         "positions would reduce what is available here)",
                   margin_needed=float(margin))
        return out
    # The band is a wish; the account is the fact. Without this line a $50 base keeps asking for the same
    # $50-$200 the $101k demo asks for, which is 100-400% of it, and every order dies at the broker with
    # "not enough money" instead of being sized to what the account can actually lose.
    if out["equity_known"] and max_frac > 0 and risk > max_frac * float(equity):
        out["risk_capped_from"] = out["risk_asked"]
        out["capped"] = True
        risk = max_frac * float(equity)
        out["risk"] = round(risk, 2)
    wanted = (risk / per_lot) if (per_lot and risk) else 0.0
    out["lots_wanted"] = round(wanted, 6)
    v = round(math.floor(wanted / vstep + 1e-9) * vstep, 6) if vstep > 0 else round(wanted, 6)
    if v > vmax + 1e-12:
        out.update(lots=0.0, risk=round(v * per_lot, 2), verdict="over_max_lot",
                   why="would need %.4f lots, above the %.4f maximum the broker allows on %s" % (v, vmax, sym))
        return out
    if v < vmin - 1e-12:
        out["risk"] = round(risk, 2)
        if out["equity_known"] and max_frac > 0 and out["min_lot_risk"] > max_frac * float(equity):
            pct = 100.0 * out["min_lot_risk"] / float(equity)
            out.update(lots=0.0, verdict="min_lot_too_big",
                       why="the smallest size the broker accepts (%s lot) risks $%.2f = %.1f%% of a $%.2f "
                           "account, over the %.0f%% ceiling — %s cannot be traded on this base"
                           % (vmin, out["min_lot_risk"], pct, float(equity), 100 * max_frac, sym))
            return out
        out.update(lots=vmin, risk_actual=out["min_lot_risk"], verdict="round_up_to_min_lot",
                   frac_of_equity=(round(100.0 * out["min_lot_risk"] / float(equity), 1)
                                   if out["equity_known"] else None),
                   why="risking $%.2f needs %.4f lots, below the %s minimum — sized at the minimum lot, "
                       "which risks $%.2f instead" % (risk, wanted, vmin, out["min_lot_risk"]))
        return out
    out.update(lots=v, risk_actual=round(v * per_lot, 2),
               frac_of_equity=(round(100.0 * v * per_lot / float(equity), 1) if out["equity_known"] else None))
    out["risk"] = round(v * per_lot, 2)
    if not out["equity_known"]:
        out["why"] = "equity unknown this cycle, so the min-lot ceiling was not checked"
    if out["capped"]:
        out["why"] = ("risk capped to $%.2f (%.0f%% of a $%.2f account); the band asked for $%.2f"
                      % (risk, 100 * max_frac, float(equity), out["risk_capped_from"]))
    return out

def fmt_account_line(a):
    """One line naming WHICH account this build trades and what kind of money it is.

    Composed here, in the one place that has read the terminal, so the desk page and the radar page cannot
    word the same fact differently. The account type decides the sentence: a demo base must never be able to
    read like a wallet figure, and a real one must never be able to hide behind the word "demo".
    """
    if not a:
        return ""
    bits = []
    for k, lab in (("login", "login"), ("server", "server"), ("type", "account"), ("currency", "ccy"),
                   ("margin_mode", "margin mode")):
        if a.get(k):
            bits.append("%s %s" % (lab, a[k]))
    for k, lab in (("equity", "equity"), ("balance", "balance")):
        if isinstance(a.get(k), (int, float)):
            bits.append("%s $%s" % (lab, format(a[k], ",.2f")))
    if a.get("asof"):
        bits.append("read %s" % a["asof"])
    if a.get("stale"):
        bits.append("STALE: last answered %s" % a["stale"])
    line = " · ".join(bits)
    t = str(a.get("type") or "").strip().lower()
    if t == "demo":
        line += " — a DEMO account: the orders really do go to the terminal, the money does not come from you"
    elif t in ("real", "live"):
        line += " — NOT a demo account: every order this build sends moves real money"
    elif t:
        line += " — account type reported as '%s', which this build has not seen before and will not guess at" % t
    else:
        line += " — the terminal reported no account type, so nothing here claims demo or real"
    return line


def fmt_guard_line(s):
    """The sizing floor in the build's own words: what one minimum-size position may risk, what the broker's
    minimum lot actually is, and how many candidates that floor refused today."""
    if not s:
        return ""
    eq, mf = s.get("equity"), s.get("max_frac")
    bits = []
    if isinstance(eq, (int, float)) and eq > 0 and isinstance(mf, (int, float)) and mf > 0:
        bits.append("one minimum-size position may not risk over %.0f%% of equity ($%s of $%s)"
                    % (100 * mf, format(mf * eq, ",.2f"), format(eq, ",.2f")))
    elif not isinstance(eq, (int, float)):
        bits.append("no equity read this cycle, so the min-lot ceiling was NOT applied")
    elif mf == 0:
        bits.append("min-lot ceiling switched off from the desk")
    ml = s.get("min_lot") or {}
    fl = ", ".join("%s %s lot" % (k, ml[k]) for k in sorted(ml)[:6] if ml.get(k))
    if fl:
        bits.append("broker floor: " + fl)
    mfl = s.get("margin_floor") or {}
    if mfl:
        bits.append("margin for one unit: " + ", ".join("%s $%s" % (k, format(mfl[k], ",.2f"))
                                                         for k in sorted(mfl)[:6]))
    elif ml and isinstance(eq, (int, float)) and eq > 0:
        bits.append("margin floor NOT measured, so a size this account cannot post would not be caught here")
    if s.get("risk_cap") is not None:
        bits.append("so one trade risks at most $%s here" % format(s["risk_cap"], ",.2f"))
    if s.get("capped_today"):
        bits.append("%d trade(s) today had their risk cut to that cap" % s["capped_today"])
    ref = s.get("refused_today") or {}
    if ref:
        bits.append("refused today: " + ", ".join("%s x%d" % (k, ref[k]) for k in sorted(ref)))
    return " · ".join(bits)


def fmt_live_line(live):
    """What the trades that ACTUALLY WERE SENT have done, kept apart from the paper track of rejected
    candidates. A sent order with no close yet is stated as ungraded, never as a win rate."""
    if not live:
        return ""
    sent, n = live.get("sent") or 0, live.get("graded") or 0
    if not sent:
        return "nothing sent on this account yet, so there is no live record to grade"
    if not n:
        return ("%d trades sent, 0 graded — no terminal close has matched one yet, and a sent order that has "
                "not closed is not a result" % sent)
    s = "of the %d trades SENT, %d graded from the terminal's own closes: %sW/%sL" % (
        sent, n, live.get("wins"), live.get("losses"))
    if isinstance(live.get("win_rate"), (int, float)):
        s += " (%.1f%%)" % live["win_rate"]
    if isinstance(live.get("net_r"), (int, float)):
        s += ", net %+.2fR" % live["net_r"]
    if isinstance(live.get("net_usd"), (int, float)):
        s += ", $%+.2f on the account" % live["net_usd"]
    if live.get("from_terminal"):
        s += " · %d matched on the Sentry order comment" % live["from_terminal"]
    if (live.get("ungraded") or 0) > 0:
        s += " · %d sent with no close to match yet" % live["ungraded"]
    return s

def send_order(state, sym, otype, volume, price, sl, tp, skill, risk=None):
    risk = RISK if risk is None else risk
    try:
        _cfg = json.load(open(os.path.dirname(STATE_F) + "/desk_mode.json"))
        if not _cfg.get("entries_enabled", False):
            journal_alert(f"CANDIDATE — {sym} {otype} {volume}@{price} sl{sl} tp{tp} ({skill}) — awaiting Arena desk decision")
            return False
    except Exception:
        journal_alert(f"CANDIDATE — {sym} {otype} {volume}@{price} sl{sl} tp{tp} ({skill}) — awaiting Arena desk decision")
        return False
    # ---- the live-money interlock ----
    # Everything this build has ever touched is demo money: 118 orders sent and 91 refused on 2026-11-18
    # alone, on a five-minute cycle.  The only thing that ever stood between that loop and an account that
    # can be overdrawn was one boolean in a file written for rehearsal, and a login change is all it takes
    # to repoint it.  So a real account has to be told twice, HERE — not in a page header.  Worth saying
    # out loud because it is the opposite of what people expect: the terminal's own AutoTrading switch does
    # NOT gate this path.  That switch gates EAs.  These orders go through the terminal's MCP trade API,
    # which the demo proved is stopped only by desk_mode.json, so flipping that button off changes nothing.
    _la = state.get("account") or {}
    if account_is_real() and not _cfg.get("live_confirmed"):
        journal_alert(f"REFUSED (live guard) — {sym} {otype} {volume}@{price} sl{sl} tp{tp}: the terminal "
                      f"answers as login {_la.get('login') or '?'} on {_la.get('server') or '?'}, type "
                      f"'{ACCT_KIND or 'unknown'}', and this build has not been told to treat that as a "
                      f"rehearsal. Nothing was sent. Two steps, deliberately: \"live_confirmed\": true in "
                      f"desk_mode.json, and a risk_max_frac_of_equity chosen against the balance that is "
                      f"actually in the account — the demo's ceiling is not a decision about your money.")
        return False

    comment = f"Sentry {skill}"[:31]
    otype_api = otype.replace(" ", "_")
    chk = r'''
U="http://127.0.0.1:22346/mcp"
K="$(iconv -f UTF-16LE -t UTF-8 "$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5/config/assistant.ini" 2>/dev/null | tr -d "\r" | grep -m1 -o "ApiKey=[A-Za-z0-9]*" | cut -d= -f2)"
BODY="{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"initialize\",\"params\":{\"protocolVersion\":\"2025-06-18\",\"capabilities\":{},\"clientInfo\":{\"name\":\"sentry\",\"version\":\"1.0\"}}}"
curl -sS --compressed -D /tmp/sn_hi -o /dev/null --max-time 30 -X POST "$U" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Authorization: Bearer $K" -d "$BODY"
SID=$(grep -iE "^mcp-session-id:" /tmp/sn_hi | tr -d "\r" | awk "{print \$2}")
curl -sS --compressed -o /dev/null -X POST "$U" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Mcp-Session-Id: $SID" -H "Authorization: Bearer $K" -d "{\"jsonrpc\":\"2.0\",\"method\":\"notifications/initialized\"}"
curl -sS --compressed -o /dev/null -X POST "$U" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Mcp-Session-Id: $SID" -H "Authorization: Bearer $K" -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"get_trading_open_positions\",\"arguments\":{}}}"
echo "@@CHECK"
curl -sS --compressed -o /tmp/sn_c1 -X POST "$U" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Mcp-Session-Id: $SID" -H "Authorization: Bearer $K" -d "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"trade_check_pending_order\",\"arguments\":{\"symbol\":\"__SYM__\",\"type\":\"__TYPE__\",\"volume\":__VOL__,\"price\":__PRICE__,\"sl\":__SL__,\"tp\":__TP__}}}"
sed "s/^data: *//" /tmp/sn_c1 | head -c 260
echo ""
echo "@@SEND"
curl -sS --compressed -o /tmp/sn_s1 -X POST "$U" -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" -H "MCP-Protocol-Version: 2025-06-18" -H "Mcp-Session-Id: $SID" -H "Authorization: Bearer $K" -d "{\"jsonrpc\":\"2.0\",\"id\":4,\"method\":\"tools/call\",\"params\":{\"name\":\"trade_send_pending_order\",\"arguments\":{\"symbol\":\"__SYM__\",\"type\":\"__TYPE__\",\"volume\":__VOL__,\"price\":__PRICE__,\"sl\":__SL__,\"tp\":__TP__,\"comment\":\"__COMMENT__\"}}}"
sed "s/^data: *//" /tmp/sn_s1 | head -c 1600
'''
    # The 10015 guard.  Rebound here — between the check call and the send call there is no
    # other place a price can be shaped, and no way for the two calls to disagree.  This runs
    # AFTER the entries_enabled gate on purpose: a candidate that was never going to be sent
    # is journalled with its own digits, not the terminals.
    price, sl, tp = fmt_px(sym, price), fmt_px(sym, sl), fmt_px(sym, tp)
    cmd = (chk.replace("__SYM__", sym).replace("__TYPE__", otype_api)
           .replace("__VOL__", str(volume)).replace("__PRICE__", str(price))
           .replace("__SL__", str(sl)).replace("__TP__", str(tp)).replace("__COMMENT__", comment))
    out = mac(cmd)
    res = parse_send_result(out)
    if res["rejected"]:
        journal_alert(f"CHECK/SEND FAILED {sym} {otype} {volume}@{price} sl{sl} tp{tp}: "
                      f"retcode {res['retcode'] if res['retcode'] is not None else '?'} "
                      f"{res['details'] or res['raw']}")
        return False
    if res["ok"]:
        state["orders"].append({"sym": sym, "skill": skill, "risk": risk, "type": otype,
                                **({"ticket": res["ticket"]} if res["ticket"] else {})})
        state["theme_risk"][THEME[sym]] = state["theme_risk"].get(THEME[sym], 0) + risk
        four_q = (f"**{skill} HIT — {sym}** · Indicator: playbook §5/§12/§13 stack "
                  f"· Strategy: {skill} · TFs: D1/H4 bias · H1 structure · M15/M5 trigger · "
                  f"Edge: checklist-verified 3-layer confirm, 1.5R mechanical target · "
                  f"Risk ${risk:.0f} · ticket {res['ticket'] or 'the terminal returned no id'} "
                  f"{otype} {volume}@{price} sl{sl} tp{tp}")
        journal_alert(four_q)
        if not res["ticket"]:
            # Keep one accepted reply on a single line so the parser can be pinned on the field name THIS
            # build actually uses. Without this the '?/' was repeated for six days and never explained.
            journal(f"SEND ACCEPTED WITHOUT AN ID {sym}: reply keys {res['keys']} | {res['raw']}")
        return res["ticket"] or True
    journal(f"SEND REFUSED {sym} {otype} {volume}@{price} sl{sl} tp{tp}: retcode "
            f"{res['retcode'] if res['retcode'] is not None else '?'} {res['details'] or 'no reason given'}")
    return False

REV, CONT = "rev", "cont"

def candle_engine(b):
    """Playbook §12 pattern matcher on CLOSED bars. Returns [(name, dir, kind)]."""
    out = []
    if len(b) < 4: return out
    p3, p2, p1 = b[-4], b[-3], b[-2]          # last three CLOSED
    def body(x): return abs(x["c"] - x["o"])
    def rng(x): return max(x["h"] - x["l"], 1e-9)
    def bull(x): return x["c"] > x["o"]
    ub = lambda x: x["h"] - max(x["o"], x["c"])
    lb = lambda x: min(x["o"], x["c"]) - x["l"]
    mid = lambda x: (x["o"] + x["c"]) / 2
    # singles
    if body(p1) > 0 and lb(p1) >= 2*body(p1) and ub(p1) <= 0.5*body(p1): out.append(("hammer/takuri", 1, REV))
    if body(p1) > 0 and ub(p1) >= 2*body(p1) and lb(p1) <= 0.5*body(p1): out.append(("shooting-star", -1, REV))
    if body(p1) <= 0.15*rng(p1) and lb(p1) >= 0.5*rng(p1) and ub(p1) <= 0.1*rng(p1): out.append(("dragonfly", 1, REV))
    if body(p1) <= 0.15*rng(p1) and ub(p1) >= 0.5*rng(p1) and lb(p1) <= 0.1*rng(p1): out.append(("gravestone", -1, REV))
    if body(p1) >= 0.85*rng(p1): out.append(("marubozu", 1 if bull(p1) else -1, CONT))
    # two-candle
    if bull(p1) and not bull(p2) and p1["c"] > p2["o"] and p1["o"] < p2["c"] and body(p1) > body(p2): out.append(("bull-engulfing", 1, REV))
    if not bull(p1) and bull(p2) and p1["c"] < p2["o"] and p1["o"] > p2["c"] and body(p1) > body(p2): out.append(("bear-engulfing", -1, REV))
    if bull(p1) and not bull(p2) and p1["o"] < p2["l"] and p1["c"] > mid(p2) and p1["c"] < p2["o"]: out.append(("piercing", 1, REV))
    if not bull(p1) and bull(p2) and p1["o"] > p2["h"] and p1["c"] < mid(p2) and p1["c"] > p2["o"]: out.append(("dark-cloud", -1, REV))
    if abs(p1["l"]-p2["l"]) <= 0.2*min(rng(p1),rng(p2)) and not bull(p2) and bull(p1): out.append(("tweezer-bottom", 1, REV))
    if abs(p1["h"]-p2["h"]) <= 0.2*min(rng(p1),rng(p2)) and bull(p2) and not bull(p1): out.append(("tweezer-top", -1, REV))
    if bull(p1) and not bull(p2) and body(p1) < body(p2) and p1["o"] > p2["c"] and p1["c"] < p2["o"]: out.append(("bull-harami", 1, REV))
    if not bull(p1) and bull(p2) and body(p1) < body(p2) and p1["o"] < p2["c"] and p1["c"] > p2["o"]: out.append(("bear-harami", -1, REV))
    if not bull(p2) and not bull(p1) and body(p1) < body(p2) and p1["l"] >= p2["l"]: out.append(("homing-pigeon", 1, REV))
    # three-candle
    if not bull(p3) and body(p2) < 0.5*body(p3) and bull(p1) and p1["c"] > mid(p3): out.append(("morning-star", 1, REV))
    if bull(p3) and body(p2) < 0.5*body(p3) and not bull(p1) and p1["c"] < mid(p3): out.append(("evening-star", -1, REV))
    if all(bull(x) for x in (p3,p2,p1)) and all(body(x) > 0.55*rng(x) for x in (p3,p2,p1)): out.append(("three-soldiers", 1, CONT))
    if all(not bull(x) for x in (p3,p2,p1)) and all(body(x) > 0.55*rng(x) for x in (p3,p2,p1)): out.append(("three-crows", -1, CONT))
    if bull(p1) and not bull(p2) and not bull(p3) and p1["c"] > p3["h"]: out.append(("three-inside-up", 1, REV))
    if not bull(p1) and bull(p2) and bull(p3) and p1["c"] < p3["l"]: out.append(("three-inside-down", -1, REV))
    if bull(p1) and not bull(p2) and bull(p3) and body(p1) > body(p3) and p1["c"] > p3["c"]: out.append(("three-outside-up", 1, REV))
    if not bull(p1) and bull(p2) and not bull(p3) and body(p1) > body(p3) and p1["c"] < p3["c"]: out.append(("three-outside-down", -1, REV))
    return out

def level_prox(px, levels, a):
    return any(abs(px - lv) <= 0.5 * a for lv in levels)

def main():
    use_fallback()
    discover_symbols()
    journal_alert("Sentry online — playbook v3.1 · S1/S2/S4 mechanical + CRYPTO 24/7 · self-sizing "
            f"${MIN_RISK:.0f}-${MAX_RISK:.0f} (baseline ${RISK:.0f} · accuracy-scaled) · score>=4 · "
            f"cap {MAX_SENTRY_ORDERS_DAY}/day ADVISORY · "
            f"themes {THEME_CAP} · pending-only · red-window ban 20:15-22:30 KL (crypto exempt)")
    while True:
        state = load_state()
        try:
            # re-resolve symbols every 6h so broker renames / new listings are picked up
            slot_r = kl_now().strftime("%Y-%m-%d") + "H" + str(kl_now().hour // 6)
            if state.get("resolve_slot") != slot_r:
                state["resolve_slot"] = slot_r
                discover_symbols()
            out = mac(build_fetch(need_hist=has_ungraded_sent()))
            secs = out.split("@@")
            quotes, tf_map, positions, bridge = {}, {}, "", "down"
            acct_raw, hist_raw = "", ""
            cur = None
            for s in secs:
                if s.startswith("QUOTES"): quotes = parse_quotes(s[6:])
                elif s.startswith("B "):
                    parts = s.split()[:3]
                    tf_map.setdefault(parts[2], {})[parts[1]] = parse_bars(s)
                elif s.startswith("POSITIONS"): positions = s[10:]
                elif s.startswith("BRIDGE"): bridge = s[7:].strip()
                elif s.startswith("ACCOUNT"): acct_raw = s[7:]
                elif s.startswith("HISTORY"): hist_raw = s[7:]
            open_orders = re.findall(r'"order_id": "(\d+)".*?"symbol": "([A-Za-z0-9._\-]+)".*?"type": "([\w ]+)".*?"state": "(\w+)".*?"price_order": ([0-9.]+)', positions, re.S)
            bridge = "up" if str(bridge).strip().lower().startswith("up") else "down"
            state["bridge"] = bridge
            MARGIN.update({str(k): float(v) for k, v in (state.get("margin_floor") or {}).items()
                       if isinstance(v, (int, float))})
            acc = parse_account(acct_raw)
            if acc.get("equity") is not None:
                acc["asof"] = kl_now().strftime("%Y-%m-%d %H:%M:%S KL")
                state["account"] = acc
                note_account_kind(acc)   # the send guard reads this, not a page
                state["_equity"] = acc["equity"]
            elif acct_raw.strip():
                journal(f"account reply arrived but carried no parsable equity ({len(acct_raw)} chars) — the "
                        "min-lot ceiling is NOT applied this cycle; sizes are checked against the broker floor only")
            else:
                # bridge down, or a terminal that will not answer: say which account we are still assuming
                if state.get("account"):
                    state["account"]["stale"] = kl_now().strftime("%Y-%m-%d %H:%M KL")
                journal("no account reply this cycle — sizing continues without an equity ceiling; the last "
                        "known account is held on the desk marked stale")
            if state.get("bridge_prev") != bridge:
                state["bridge_prev"] = bridge
                if bridge == "down":
                    journal_alert("TERMINAL UNREACHABLE — the MT5 bridge did not answer this cycle, so the "
                                  "quotes and candles just parsed may be leftovers from the previous run. The "
                                  "scan keeps running for the record, but nothing can be sent while the "
                                  "terminal is closed: start MetaTrader 5, the bridge lives inside it.")
                else:
                    journal("bridge UP again — the terminal is answering; quotes are live from this cycle")
            if not SYMS:
                use_fallback()
                journal("universe empty — restored classic five (self-heal)")
            if bridge == "down":
                journal(f"scan DEGRADED — bridge DOWN · quotes {list(quotes)} · book items "
                        f"{len(open_orders)} (prices may be from the last cycle that reached the terminal)")
            else:
                journal(f"scan ok — quotes {list(quotes)} · book items {len(open_orders)}")
            # One broker round-trip per symbol never yet measured. Cached in state.json because the answer
            # moves with price by cents while a wrong or missing answer changes what the account can trade,
            # and because a restart should not have to ask again to stay safe.
            if quotes:
                _todo = [s for s in SYMS if s not in MARGIN]
                if _todo:
                    _mc = {}
                    for _s in _todo[:10]:
                        _m = measure_margin(_s, quotes, (state.get("account") or {}).get("currency"))
                        if _m:
                            MARGIN[_s] = _m
                            _mc[_s] = _m
                    if _mc:
                        journal("margin floor measured (broker's own calc): "
                                + ", ".join("%s $%.2f" % (k, _mc[k]) for k in sorted(_mc)))
                    _miss = [s for s in _todo if s not in MARGIN]
                    if _miss:
                        journal("NOTE — margin floor NOT measured for " + ", ".join(_miss)
                                + ": the terminal would not answer trade_order_calc_margin, so the only size"
                                  " check on those symbols is the risk one. On a small account that is not the"
                                  " same as being clear to trade.")
                state["margin_floor"] = dict(MARGIN)
            chart_thin = {}             # which symbol was skipped this cycle, and for want of what
            for sym in quotes:
                tf = tf_map.get(sym, {})
                m5 = tf.get("M5", []); m15 = tf.get("M15", []); h1 = tf.get("H1", [])
                h4 = tf.get("H4", []); d1 = tf.get("D1", [])
                _thin = {t: len(b) for b, t in ((m5, "M5"), (m15, "M15"), (h1, "H1"), (h4, "H4"), (d1, "D1"))
                         if len(b) < TF_MIN[t]}
                if _thin:
                    chart_thin[sym] = _thin     # disclosed, not swallowed — see publish_watch
                    continue
                bid, ask = quotes[sym]["bid"], quotes[sym]["ask"]
                c1 = [b["c"] for b in h1]
                a = atr(h1); e20 = ema(c1, 20); e50 = ema(c1, 50); e20v = e20[-1]
                r15 = rsi([b["c"] for b in m15]); r5_2 = rsi([b["c"] for b in m5], 2)
                bb = bollinger(c1); hi, lo = pivots(h1); tr = trend(hi, lo)
                if a <= 0: continue
                # HTF bias from D1 structure (closed bars)
                d1c = d1[-2]["c"]; d1ref = d1[-12]["c"] if len(d1) >= 12 else d1[0]["c"]
                htf = 1 if d1c > d1ref * 1.001 else (-1 if d1c < d1ref * 0.999 else 0)
                h4c = [b["c"] for b in h4]; h4e20 = ema(h4c, 20)[-1]
                levels = list(hi[-3:]) + list(lo[-3:]) + [e20v]
                near = level_prox(bid, levels, a)
                avg_body = sum(abs(x["c"] - x["o"]) for x in m15[-20:]) / 20
                def dup(otype, price):
                    for (_, s2, t2, st2, p2x) in open_orders:
                        if s2 == sym and otype.split()[0] in t2 and st2 == "placed" and abs(float(p2x) - price) < 1.5 * a:
                            return True
                    return False
                def fire(skill, kind_dir, otype, entry, sl, tp, score, base_risk):
                    is_crypto = sym in CRYPTO_SET
                    if not is_crypto and red_window(): return   # crypto runs 24/7 incl. red window
                    if sym in EQUITY_SET and not equity_window_open(): return
                    fkey = f"FIRE|{sym}|{skill}|{state.get('day','')}"
                    done = state.setdefault("fired_today", [])
                    if fkey in done: return
                    risk = self_size(skill, score)   # v3.1: Sentry sizes itself off its own accuracy
                    # v4.8.0: record WHAT the gate judged. The 2026-11-20 audit could not settle whether the
                    # losing candle-long trades fired on agreement or merely on nobody objecting, because
                    # htf/tr were never stored. Every row now carries them, so that question is answerable at
                    # n=100 with three grep-able fields instead of not at all.
                    ctx = {"htf": htf, "tr": tr, "atr": round(a, 8), "near": bool(near)}
                    if score < (3 if is_crypto else 4):   # crypto gets a 3/5 shot at floor size
                        done.append(fkey); del done[:-200]
                        rid = f"{sym}|{skill}|{entry:.5f}"
                        tl_log({"rid": rid, "sym": sym, "skill": skill, "otype": otype, "entry": entry, "sl": sl, "tp": tp, "score": score, "risk": risk, "fired": False, **ctx})
                        state.setdefault("paper", []).append({"rid": rid, "sym": sym, "skill": skill, "otype": otype, "entry": entry, "sl": sl, "tp": tp, "t": time.time(), "score": score})
                        del state["paper"][:-60]
                        journal_alert(f"CANDIDATE(score {score}/5) — {sym} {skill} {otype} {rnd(sym,entry)} sl{rnd(sym,sl)} tp{rnd(sym,tp)} — below auto-fire gate, desk review")
                        return
                    th = THEME[sym]
                    used = book_theme_risk(positions) or state.get("theme_risk", {})
                    if used.get(th, 0) + risk > THEME_CAP[th]:
                        journal_alert(f"NOTE — {sym} {skill}: theme exposure ${used.get(th,0)+risk:.0f} ({th}) over soft cap — advisory only, FULL FREEDOM mode")
                    if len(state["orders"]) >= MAX_SENTRY_ORDERS_DAY:
                        journal_alert(f"NOTE — {sym} {skill}: entry #{len(state['orders'])+1} today over soft cap — advisory only, FULL FREEDOM mode")
                    if dup(otype, entry): return
                    rep = size_report(sym, abs(sl - entry), risk, state.get("_equity"), risk_max_frac(),
                                        margin=MARGIN.get(sym))
                    if rep["verdict"] not in ("ok", "round_up_to_min_lot"):
                        # This used to be the build's loudest silence: sz() returned 0 when the size the risk
                        # implied was under the broker's minimum lot, and the candidate simply vanished.
                        tl_log({"rid": f"{sym}|{skill}|{entry:.5f}", "sym": sym, "skill": skill, "otype": otype,
                                "entry": entry, "sl": sl, "tp": tp, "score": score, "risk": risk, "fired": False,
                                "vol": rep["lots"], "refuse": rep["verdict"], "why": rep["why"], **ctx})
                        journal_alert(f"REFUSED — {sym} {skill}: {rep['why']}")
                        return
                    v = rep["lots"]
                    risk = rep["risk_actual"] or rep["risk"] or risk
                    if rep.get("capped"):
                        journal_alert(f"NOTE — {sym} {skill}: {rep['why']}")
                    if rep["verdict"] == "round_up_to_min_lot":
                        journal_alert(f"NOTE — {sym} {skill}: {rep['why']}")
                    # Costs nothing to check and refuses nothing that would have been sent: the
                    # terminal declines this order anyway, so all that changes is that we say why, once,
                    # and the day's count of held candidates becomes visible instead of 90 lines of
                    # "Invalid price".  The candidate itself stays un-burnt — fired_today is NOT marked,
                    # because if the market pulls back the level becomes valid again and the signal was
                    # real; only the journalling is deduplicated per level.
                    gok, gwhy = pending_geom(sym, otype, entry, sl, tp, bid, ask)
                    if not gok:
                        _gkey = f"{sym}|{skill}|{otype}|{entry:.5f}"
                        _gseen = state.setdefault("geom_seen", [])
                        state["geom_held"] = int(state.get("geom_held") or 0) + 1
                        if _gkey not in _gseen:
                            _gseen.append(_gkey); del _gseen[:-200]
                            tl_log({"rid": f"{sym}|{skill}|{entry:.5f}", "sym": sym, "skill": skill,
                                    "otype": otype, "entry": entry, "sl": sl, "tp": tp, "score": score,
                                    "risk": risk, "fired": False, "vol": v,
                                    "refuse": "level_crossed_before_send", "why": gwhy, **ctx})
                            journal_alert(f"HELD — {sym} {skill}: {gwhy}")
                        return
                    ok = bool(v) and send_order(state, sym, otype, v, entry, sl, tp, skill, risk)
                    tid = ok if isinstance(ok, str) else None
                    ok = bool(ok)
                    rec = {"rid": f"{sym}|{skill}|{entry:.5f}", "sym": sym, "skill": skill, "otype": otype,
                           "entry": entry, "sl": sl, "tp": tp, "score": score, "risk": risk, "fired": ok,
                           "vol": v, **ctx}
                    if tid: rec["ticket"] = tid
                    if rep["verdict"] == "round_up_to_min_lot":
                        rec["upsized_from"] = rep["risk_asked"]
                    if rep.get("capped"):
                        rec["capped_from"] = rep["risk_capped_from"]
                    tl_log(rec)
                    if ok:
                        done.append(fkey); del done[:-200]
                # ---- S1 trend pullback ----
                if tr == "down" and e20v > bid + 0.05 * a and abs(e20v - bid) < 0.9 * a and 40 <= r15 <= 55:
                    sl = (hi[-1] if hi else e20v + a) + 0.25 * a
                    if sl > e20v:
                        fire("S1-pullback-short", -1, "sell limit", e20v, sl, e20v - 1.5*(sl-e20v), 4 if near else 3, 100.0)
                if tr == "up" and e20v < bid - 0.05 * a and abs(bid - e20v) < 0.9 * a and 45 <= r15 <= 60:
                    sl = (lo[-1] if lo else e20v - a) - 0.25 * a
                    if sl < e20v:
                        fire("S1-pullback-long", 1, "buy limit", e20v, sl, e20v + 1.5*(e20v-sl), 4 if near else 3, 100.0)
                # ---- S2 breakdown / level continuation ----
                if tr == "down" and lo and 0 <= bid - lo[-1] < 0.35 * a:
                    lvl = lo[-1]; sl = (hi[-1] if hi else bid) + 0.25 * a
                    if sl > lvl - 0.25*a:
                        e = lvl - 0.25*a
                        fire("S2-breakdown-short", -1, "sell stop", e, sl, e - 1.5*(sl-e), 4 if near else 3, 100.0)
                if tr == "up" and hi and 0 <= hi[-1] - bid < 0.35 * a:
                    lvl = hi[-1]; sl = (lo[-1] if lo else bid) - 0.25 * a
                    e = lvl + 0.25*a
                    fire("S2-breakout-long", 1, "buy stop", e, sl, e + 1.5*(e-sl), 4 if near else 3, 100.0)
                # ---- S4/S18 range fades ----
                if bb and tr == "none":
                    lower, midb, upper = bb
                    if bid <= lower * 1.001 and r15 < 32:
                        fire("S4-band-fade-long", 1, "buy limit", lower, bid - 0.6*a, midb, 4 if r15 < 25 else 3, 100.0)
                    if bid >= upper * 0.999 and r15 > 68:
                        fire("S4-band-fade-short", -1, "sell limit", upper, bid + 0.6*a, midb, 4 if r15 > 75 else 3, 100.0)
                if r5_2 < 10 and bid > e20v and tr != "down":
                    fire("S18-rsi2-long", 1, "buy limit", bid, bid - 1.2*a, bid + 1.5*a, 4 if near else 3, 100.0)
                if r5_2 > 90 and bid < e20v and tr != "up":
                    fire("S18-rsi2-short", -1, "sell limit", bid, bid + 1.2*a, bid - 1.5*a, 4 if near else 3, 100.0)
                if abs(bid - e20v) > 2.5 * a:
                    if bid < e20v and tr == "none": fire("S18-ma-revert-long", 1, "buy limit", bid, bid - 1.0*a, e20v, 3, 100.0)
                    if bid > e20v and tr == "none": fire("S18-ma-revert-short", -1, "sell limit", bid, bid + 1.0*a, e20v, 3, 100.0)
                # ---- S10 MA cross (H1 closed) ----
                if len(e20) >= 3 and len(e50) >= 3:
                    if e20[-2] <= e50[-2] and e20[-1] > e50[-1] and htf >= 0:
                        fire("S10-ma-cross-long", 1, "buy stop", bid + 0.2*a, bid - 1.2*a, bid + 2.4*a, 4 if htf > 0 else 3, 100.0)
                    if e20[-2] >= e50[-2] and e20[-1] < e50[-1] and htf <= 0:
                        fire("S10-ma-cross-short", -1, "sell stop", bid - 0.2*a, bid + 1.2*a, bid - 2.4*a, 4 if htf < 0 else 3, 100.0)
                # ---- S11 Donchian 20/55 (H1 closed) ----
                sig1 = h1[-2]
                for n, tag in ((20, "S11-dc20"), (55, "S11-dc55")):
                    ch = h1[-(n+1):-2]
                    if len(ch) < 10: continue
                    hh = max(x["h"] for x in ch); ll = min(x["l"] for x in ch)
                    if sig1["c"] > hh and htf >= 0: fire(f"{tag}-long", 1, "buy stop", hh + 0.1*a, hh - 0.6*a, hh + 2.2*a, 4 if htf > 0 else 3, 100.0)
                    if sig1["c"] < ll and htf <= 0: fire(f"{tag}-short", -1, "sell stop", ll - 0.1*a, ll + 0.6*a, ll - 2.2*a, 4 if htf < 0 else 3, 100.0)
                # ---- S13 Ichimoku proxy (H1) ----
                if len(h1) >= 30:
                    tenkan = (max(x["h"] for x in h1[-10:-1]) + min(x["l"] for x in h1[-10:-1])) / 2
                    kijun = (max(x["h"] for x in h1[-27:-1]) + min(x["l"] for x in h1[-27:-1])) / 2
                    cloud = (max(x["h"] for x in h1[-53:-1]) + min(x["l"] for x in h1[-53:-1])) / 2 if len(h1) >= 54 else kijun
                    if tenkan > kijun and bid > cloud and sig1["c"] > tenkan:
                        fire("S13-ichimoku-long", 1, "buy stop", bid + 0.15*a, kijun - 0.3*a, bid + 2.2*a, 4 if htf > 0 else 3, 100.0)
                    if tenkan < kijun and bid < cloud and sig1["c"] < tenkan:
                        fire("S13-ichimoku-short", -1, "sell stop", bid - 0.15*a, kijun + 0.3*a, bid - 2.2*a, 4 if htf < 0 else 3, 100.0)
                # ---- S15 squeeze + S16 inside compression ----
                if bb:
                    avg_rng = sum(x["h"] - x["l"] for x in h1[-60:]) / 60
                    if (sig1["h"] - sig1["l"]) < 0.6 * avg_rng and sig1["c"] > bb[2]:
                        fire("S15-squeeze-long", 1, "buy stop", bb[2] + 0.1*a, bb[1], bb[2] + 2*(bb[2]-bb[1]), 4, 100.0)
                    if (sig1["h"] - sig1["l"]) < 0.6 * avg_rng and sig1["c"] < bb[0]:
                        fire("S15-squeeze-short", -1, "sell stop", bb[0] - 0.1*a, bb[1], bb[0] - 2*(bb[1]-bb[0]), 4, 100.0)
                p2, p3 = m15[-2], m15[-3]
                if len(m15) >= 8:
                    expn = max(m15[-8:-3], key=lambda x: x["h"] - x["l"])
                    if (expn["h"] - expn["l"]) > 1.2 * a and p2["h"] < p3["h"] and p2["l"] > p3["l"]:
                        fire("S16-inside-long", 1, "buy stop", p3["h"] + 0.1*a, p3["l"] - 0.25*a, p3["h"] + 1.5*a, 4 if htf >= 0 else 3, 100.0)
                        fire("S16-inside-short", -1, "sell stop", p3["l"] - 0.1*a, p3["h"] + 0.25*a, p3["l"] - 1.5*a, 4 if htf <= 0 else 3, 100.0)
                # ---- S21 pivot break (prev D1 pivots, M5 confirm) ----
                if len(d1) >= 3:
                    pd = d1[-3]
                    P = (pd["h"] + pd["l"] + pd["c"]) / 3; R1 = 2*P - pd["l"]; S1 = 2*P - pd["h"]
                    if m5[-2]["c"] > R1 > bid - a and htf >= 0:
                        fire("S21-pivot-R1-long", 1, "buy stop", R1 + 0.1*a, P, R1 + 2*(R1-P), 4 if htf > 0 else 3, 100.0)
                    if m5[-2]["c"] < S1 < bid + a and htf <= 0:
                        fire("S21-pivot-S1-short", -1, "sell stop", S1 - 0.1*a, P, S1 - 2*(P-S1), 4 if htf < 0 else 3, 100.0)
                # ==== PACK16 ADVANCED SKILLS ====
                # ---- S3 momentum continuation (playbook S3) ----
                sbar = h1[-2]
                sbar_rng = max(sbar["h"] - sbar["l"], 1e-9)
                if tr == "up" and sbar["c"] > sbar["o"] and sbar["c"] > e20v and e20v > e50[-1] and (sbar["c"] - sbar["o"]) > 0.45 * a and htf >= 0:
                    fire("S3-momentum-long", 1, "buy stop", sbar["h"] + 0.1*a, sbar["l"] - 0.2*a, sbar["h"] + 2.0*(sbar_rng + 0.3*a), 4 if htf > 0 else 3, 100.0)
                if tr == "down" and sbar["c"] < sbar["o"] and sbar["c"] < e20v and e20v < e50[-1] and (sbar["o"] - sbar["c"]) > 0.45 * a and htf <= 0:
                    fire("S3-momentum-short", -1, "sell stop", sbar["l"] - 0.1*a, sbar["h"] + 0.2*a, sbar["l"] - 2.0*(sbar_rng + 0.3*a), 4 if htf < 0 else 3, 100.0)
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
                            e = m15[-2]["l"] - 0.1*a; slx = m15[ib]["h"] + 0.25*a
                            fire("S22-rsi-bear-div", -1, "sell stop", e, slx, e - 1.5*(slx-e), 4 if htf <= 0 else 3, 100.0)
                    if len(swL) >= 2:
                        ia, ib = swL[-2], swL[-1]
                        ra = rsi(r15c[:ia+1]); rb = rsi(r15c[:ib+1])
                        if m15[ib]["l"] < m15[ia]["l"] and rb > ra + 1 and m15[-2]["c"] > m15[-2]["o"]:
                            e = m15[-2]["h"] + 0.1*a; slx = m15[ib]["l"] - 0.25*a
                            fire("S22-rsi-bull-div", 1, "buy stop", e, slx, e + 1.5*(e-slx), 4 if htf >= 0 else 3, 100.0)
                # ---- S23 liquidity sweep: spring / upthrust (Wyckoff) ----
                if len(h1) >= 12:
                    sbar = h1[-2]; sbar_rng = max(sbar["h"] - sbar["l"], 1e-9)
                    prior_hi = max(x["h"] for x in h1[-11:-2])
                    prior_lo = min(x["l"] for x in h1[-11:-2])
                    up_wick = sbar["h"] - max(sbar["o"], sbar["c"])
                    dn_wick = min(sbar["o"], sbar["c"]) - sbar["l"]
                    if sbar["l"] < prior_lo and sbar["c"] > prior_lo and dn_wick > 0.5 * sbar_rng:
                        fire("S23-spring-long", 1, "buy stop", sbar["h"] + 0.1*a, sbar["l"] - 0.25*a, sbar["h"] + 1.6*(sbar_rng + 0.35*a), 4 if htf >= 0 else 3, 100.0)
                    if sbar["h"] > prior_hi and sbar["c"] < prior_hi and up_wick > 0.5 * sbar_rng:
                        fire("S23-upthrust-short", -1, "sell stop", sbar["l"] - 0.1*a, sbar["h"] + 0.25*a, sbar["l"] - 1.6*(sbar_rng + 0.35*a), 4 if htf <= 0 else 3, 100.0)
                # ---- S24 Fibonacci 0.5-0.618 pullback continuation ----
                if len(hi) >= 1 and len(lo) >= 1 and hi[-1] > lo[-1]:
                    lastH, lastL = hi[-1], lo[-1]
                    z_lo = lastH - 0.618 * (lastH - lastL); z_hi = lastH - 0.5 * (lastH - lastL)
                    if tr == "up" and z_lo <= bid <= z_hi and h1[-2]["c"] > h1[-2]["o"]:
                        fire("S24-fib-long", 1, "buy stop", h1[-2]["h"] + 0.1*a, z_lo - 0.5*a, h1[-2]["h"] + 1.5*(max(h1[-2]["h"]-h1[-2]["l"], 1e-9) + 0.4*a), 4 if htf > 0 else 3, 100.0)
                    z_lo2 = lastL + 0.5 * (lastH - lastL); z_hi2 = lastL + 0.618 * (lastH - lastL)
                    if tr == "down" and z_lo2 <= bid <= z_hi2 and h1[-2]["c"] < h1[-2]["o"]:
                        fire("S24-fib-short", -1, "sell stop", h1[-2]["l"] - 0.1*a, z_hi2 + 0.5*a, h1[-2]["l"] - 1.5*(max(h1[-2]["h"]-h1[-2]["l"], 1e-9) + 0.4*a), 4 if htf < 0 else 3, 100.0)
                # ---- S25 session-range breakout (London / NY open) ----
                srv_h = (kl_now().hour - 6) % 24
                if srv_h in (9, 16) and len(h1) >= 3:
                    anchor = h1[-3]; ah, al = anchor["h"], anchor["l"]
                    if ah > al and h1[-2]["c"] > ah and bid > ah and htf >= 0:
                        fire("S25-session-break-long", 1, "buy stop", ah + 0.1*a, al - 0.2*a, ah + 1.8*(ah - al + 0.3*a), 4 if htf > 0 else 3, 100.0)
                    if ah > al and h1[-2]["c"] < al and bid < al and htf <= 0:
                        fire("S25-session-break-short", -1, "sell stop", al - 0.1*a, ah + 0.2*a, al - 1.8*(ah - al + 0.3*a), 4 if htf < 0 else 3, 100.0)
                # ---- §12 CANDLE LIBRARY on H1 + M15 (closed bars) ----
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
                        seen = state.setdefault("seen_candles", [])
                        if key in seen: continue
                        seen.append(key); del seen[:-300]
                        at_lvl = level_prox((sig["h"]+sig["l"])/2, levels, a)
                        big = abs(sig["c"] - sig["o"]) > avg_body if tflabel == "M15" else abs(sig["c"] - sig["o"]) > 0.5*a
                        close_ext = (direction == 1 and sig["c"] > (sig["h"]+sig["l"])/2) or (direction == -1 and sig["c"] < (sig["h"]+sig["l"])/2)
                        # v4.8.0: a candle signal needs a bias that AGREES with it, not merely one that stays
                        # out of the way. `htf in (0, direction)` gave the point to a FLAT daily, so the entry
                        # condition was "a pattern appeared and nothing objected" — on the live record C-* longs
                        # ran -0.426R over 25 trades (total -10.65R) while every S-* long leg already requires
                        # htf == direction. Applied to BOTH sides on purpose: a flat daily with flat structure now
                        # refuses shorts too, so this is a confluence rule and not a fit to one down week. What
                        # it drops still reaches the paper book at score 3, so it grades its own counterfactual.
                        agrees = (htf == direction) or (tr == ("up" if direction > 0 else "down"))
                        rr_ok = True
                        score = sum([at_lvl, big, close_ext, agrees, rr_ok])
                        skill = f"C-{tflabel}-{name}"
                        if direction == 1:
                            e = sig["h"] + 0.1*a; sl = sig["l"] - 0.25*a
                            fire(skill, 1, "buy stop", e, sl, e + 1.5*(e-sl), score, 100.0)
                        else:
                            e = sig["l"] - 0.1*a; sl = sig["h"] + 0.25*a
                            fire(skill, -1, "sell stop", e, sl, e - 1.5*(sl-e), score, 100.0)
            # ---- housekeeping: fills, breakeven, T11 day-window ----
            poss = parse_positions(positions)
            known = set(state.get("known_positions", []))
            if "known_positions" not in state:
                for p in poss:
                    journal(f"position adopted on book: {p['sym']} {p['action']} {p['vol']}@{p['open']} sl{p['sl']} tp{p['tp']}")
                state["known_positions"] = [p["id"] for p in poss]
            else:
                for p in poss:
                    if p["id"] not in known:
                        state["known_positions"].append(p["id"])
                        journal_alert(f"FILL — {p['sym']} {p['action']} {p['vol']}@{p['open']} sl{p['sl']} tp{p['tp']} profit {p['profit']} | ticket {p['id']}")
            # ---- outcome tracking: join the terminal's own closes back onto our sent trades ----
            # v4.7.8 and before called mcp_call("get_trading_history_positions") here. mcp_call truncates its
            # reply to 300 bytes, so the reply never parsed, the except swallowed it, and NO sent trade was
            # ever graded - while the paper track of REJECTED candidates collected all the win-rate credit.
            # The history now arrives uncapped in the same FETCH, and only while a trade is outstanding.
            rows_now = tl_rows()
            closed_now = parse_closed(hist_raw) if hist_raw.strip() else []
            if closed_now:
                # v4.8.0: no `known_tickets` here. The fix that stopped match_closes re-using a consumed close
                # landed INSIDE the function (see its `used` set, built from rows that already have a result),
                # but this caller then re-imposed it by feeding in every ticket in the ledger — which excludes
                # each UNGRADED row's own close, i.e. exactly the trade being graded. v4.7.9's send-parsing
                # hardening is what made it bite: once rows started carrying tickets reliably, every new trade
                # became ungradeable. Measured on the live account 2026-11-20: the deployed join found 0
                # matches as called and 38 as written; the desk published 36 graded trades while 121 existed.
                wrote = 0
                for u in match_closes(rows_now, closed_now):
                    pf = ("%+.2f" % u["profit"]) if u.get("profit") is not None else "n/a"
                    rr = (", %+.2fR" % u["R"]) if u.get("R") is not None else ""
                    if tl_grade_terminal(u):
                        wrote += 1
                        journal_alert(f"OUTCOME — {u['sym']} {u['skill']} closed {pf} ({u['result'].upper()}{rr})"
                                      f" | ticket {u['ticket']}, matched by {u['via']}")
                if wrote:
                    rows_now = tl_rows()
                    state["reconcile"] = {"graded_this_cycle": wrote,
                                          "at": kl_now().strftime("%Y-%m-%d %H:%M:%S KL")}
                state["closed_tracked"] = [c["ticket"] for c in closed_now][-150:]
            state["closed_seen"] = len(closed_now) or None
            state["live_record"] = live_record(rows_now, (state.get("account") or {}).get("currency"))
            refus = {}
            for r in rows_now:
                if r.get("refuse") and str(r.get("ts", "")).startswith(str(state.get("day") or "")):
                    refus[r["refuse"]] = refus.get(r["refuse"], 0) + 1
            capped = sum(1 for r in rows_now
                         if r.get("capped_from") and str(r.get("ts", "")).startswith(str(state.get("day") or "")))
            state["sizing"] = {"equity": state.get("_equity"), "max_frac": risk_max_frac(),
                               "risk_cap": (round(risk_max_frac() * state["_equity"], 2)
                                            if isinstance(state.get("_equity"), (int, float)) and risk_max_frac() > 0
                                            else None),
                               "capped_today": capped,
                               "guard_on": bool(state.get("_equity")) and risk_max_frac() > 0,
                               "refused_today": refus, "min_lot": {s: VSPEC.get(s, (0.01, 0.01, 1e6))[0]
                                                                   for s in (SYMS or [])[:10]},
                               "margin_floor": {s: MARGIN[s] for s in (SYMS or []) if s in MARGIN},
                               "contract": {s: MULT.get(s) for s in (SYMS or [])[:10]}}
            state["account_line"] = fmt_account_line(state.get("account") or {})
            state["guard_line"] = fmt_guard_line(state.get("sizing") or {})
            state["live_line"] = fmt_live_line(state.get("live_record") or {})
            for p in poss:
                if p["sl"] == 0: continue
                r_dist = abs(p["open"] - p["sl"])
                if r_dist == 0: continue
                if p["action"] == "buy" and p["last"] >= p["open"] + r_dist and p["sl"] < p["open"]:
                    j = mcp_call("trade_modify_sl_tp", '{"symbol": "%s", "position_ticket": "%s", "sl": %s}' % (p["sym"], p["id"], p["open"]))
                    journal_alert(f"BE moved +1R: {p['sym']} buy {p['id']} SL->{p['open']} | {j[-80:]}")
                if p["action"] == "sell" and p["last"] <= p["open"] - r_dist and p["sl"] > p["open"]:
                    j = mcp_call("trade_modify_sl_tp", '{"symbol": "%s", "position_ticket": "%s", "sl": %s}' % (p["sym"], p["id"], p["open"]))
                    journal_alert(f"BE moved +1R: {p['sym']} sell {p['id']} SL->{p['open']} | {j[-80:]}")
            # ---- chandelier trail: after +1.5R trail SL at 2xATR (playbook 8) ----
            for p in poss:
                if p["sl"] == 0: continue
                r_dist = abs(p["open"] - p["sl"])
                if r_dist == 0: continue
                try:
                    aa = atr(tf_map.get(p["sym"], {}).get("H1", []) or [])
                    if aa <= 0: continue
                    if p["action"] == "buy" and p["last"] >= p["open"] + 1.5 * r_dist:
                        new_sl = p["last"] - 2 * aa
                        if new_sl > p["sl"]:
                            j = mcp_call("trade_modify_sl_tp", '{"symbol": "%s", "position_ticket": "%s", "sl": %s}' % (p["sym"], p["id"], fmt_px(p["sym"], new_sl)))
                            journal_alert(f"TRAIL 2xATR: {p['sym']} buy {p['id']} SL->{fmt_px(p['sym'], new_sl)} | {j[-60:]}")
                except Exception:
                    pass
                try:
                    aa = atr(tf_map.get(p["sym"], {}).get("H1", []) or [])
                    if aa <= 0: continue
                    if p["action"] == "sell" and p["last"] <= p["open"] - 1.5 * r_dist:
                        new_sl = p["last"] + 2 * aa
                        if new_sl < p["sl"]:
                            j = mcp_call("trade_modify_sl_tp", '{"symbol": "%s", "position_ticket": "%s", "sl": %s}' % (p["sym"], p["id"], fmt_px(p["sym"], new_sl)))
                            journal_alert(f"TRAIL 2xATR: {p['sym']} sell {p['id']} SL->{fmt_px(p['sym'], new_sl)} | {j[-60:]}")
                except Exception:
                    pass
            # T11: day-scope equity flat at window end (backoff: max 3 attempts per ticket per day)
            if not equity_window_open() and EQUITY_SET:
                fails = state.setdefault("t11_fail", {})
                for p in poss:
                    if p["sym"] in EQUITY_SET and fails.get(p["id"], 0) < 3:
                        j = mcp_call("trade_close_single_position", '{"symbol": "%s", "position_ticket": "%s"}' % (p["sym"], p["id"]))
                        bad = ("error" in j) or ("isError" in j)
                        fails[p["id"]] = fails.get(p["id"], 0) + 1 if bad else 0
                        if not bad or fails[p["id"]] <= 1:
                            journal_alert(f"T11 window end: closing {p['sym']} position {p['id']} (day-scope) | {j[-80:]}")
                for (_, s2, t2, st2, p2) in open_orders:
                    if s2 in EQUITY_SET and st2 == "placed" and fails.get("O" + _, 0) < 3:
                        j = mcp_call("trade_delete_order", '{"symbol": "%s", "order_ticket": "%s"}' % (s2, _))
                        bad = ("error" in j) or ("isError" in j)
                        fails["O" + _] = fails.get("O" + _, 0) + 1 if bad else 0
                        if not bad or fails["O" + _] <= 1:
                            journal_alert(f"T11 window end: deleting {s2} pending {_} @{p2} (day-scope) | {j[-80:]}")
            # ---- paper counterfactuals: would skipped candidates have won? ----
            try:
                still = []
                for p in state.get("paper", []):
                    res = None
                    for b in (tf_map.get(p["sym"], {}).get("M15", []) or []):
                        t = b.get("t", 0)
                        if isinstance(t, (int, float)) and t > 1e9 and t <= p.get("t", 0): continue
                        if "buy" in p["otype"]:
                            if b["l"] <= p["sl"]: res = "loss"; break
                            if b["h"] >= p["tp"]: res = "win"; break
                        else:
                            if b["h"] >= p["sl"]: res = "loss"; break
                            if b["l"] <= p["tp"]: res = "win"; break
                    if res: tl_update_rid(p.get("rid"), res)
                    elif time.time() - p.get("t", 0) < 259200: still.append(p)
                state["paper"] = still
            except Exception:
                pass
            # ---- daily self-review ----
            slot = kl_now().strftime("%Y-%m-%d") + "H" + str(kl_now().hour // 6)
            if state.get("review_done") != slot:
                state["review_done"] = slot
                daily_review()
            # ---- heartbeat: keep the brain link warm every 6h ----
            if state.get("hb_done") != slot:
                state["hb_done"] = slot
                alert("[DESK-HEARTBEAT] " + kl_now().strftime("%H:%M") + " KL — sentry alive · book " + str(len(open_orders)) + " orders · " + str(len(poss)) + " positions · brain check-in")
        except Exception as e:
            journal_alert(f"cycle error: {e}")
        # OUTSIDE the scan's try on purpose: it must still run when a cycle errored, because "the terminal is
        # down and here is the last thing I saw" is exactly what a monitor exists to report. Its own failure
        # becomes a field — never a crash, and never a reason to skip save_state.
        try:
            publish_watch(state, quotes, tf_map, positions, chart_thin, positions)
        except Exception as _we:
            state["watch_error"] = "%s: %s" % (type(_we).__name__, str(_we)[:140])
        save_state(state)
        time.sleep(CYCLE)

if __name__ == "__main__":
    main()
