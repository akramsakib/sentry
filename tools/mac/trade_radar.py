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
import json, os, re, smtplib, subprocess, sys, threading, time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE = "/Users/sakib/hermes_sentry"
PORT = 8790
STATE_F = BASE + "/state.json"
JOURNAL_F = BASE + "/sentry_journal.md"
OUTBOX_F = BASE + "/alerts.outbox"
SENT_F = BASE + "/alerts.sent.log"
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
    try:
        r = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, timeout=6)
        ip = (r.stdout or "").strip()
    except Exception:
        return None
    ip = ip.splitlines()[0].strip() if ip else ""
    return ip if ip.count(".") == 3 and ip.startswith("100.") else None



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


def tail(path, n=12):
    try:
        with open(path) as f: return "".join(f.readlines()[-n:])
    except Exception: return ""

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
    snap["record"] = record_block()
    ip = lan_ip()
    snap["access"] = {"lan_ip": ip, "port": PORT,
                      "phone_url": ("http://%s:%d/?k=%s" % (ip, PORT, security_key())) if ip else None,
                      "tailscale_ip": tailscale_hint(), "firewall": firewall_state(),
                      "token_len": len(security_key())}
    snap["channels"] = {"gmail_cfg": os.path.exists(SMTP_F),
                        "notifier": os.path.exists(BASE + "/hermes-notifier"),
                        "webhook": os.environ.get("HERMES_ALERT_WEBHOOK", "").strip()[:60] or None,
                        "queued": _count_lines(OUTBOX_F), "sent": _count_lines(SENT_F)}
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
        import urllib.request
        req = urllib.request.Request(url, data=json.dumps({"text": line[:1000]}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=4).read()
        return True
    except Exception:
        return False


def flush_outbox():
    if not os.path.exists(OUTBOX_F): return
    with open(OUTBOX_F) as f: lines = [l.rstrip("\n") for l in f if l.strip()]
    if not lines: return
    remaining = []
    for line in lines:
        mac_notify("Hermes Trade Alert", line)
        hooked = send_webhook(line)
        # Delivered means SOMETHING OFF THE MAC GOT IT: mail, or his webhook. The notification is local to
        # this laptop and is not counted as delivery, because a laptop is not a channel when he is away.
        # Undelivered lines stay queued on disk — they are never dropped and never need a session.
        if send_gmail("Hermes Trade Alert — " + line[:60], line + "\n\n— Trade Radar / sentry") or hooked is True:
            with open(SENT_F, "a") as f: f.write(line + "\n")
        else:
            remaining.append(line)
    with open(OUTBOX_F, "w") as f: f.write("\n".join(remaining[-200:]) + ("\n" if remaining else ""))

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
<h2>Working orders</h2><table id="ord"><tr><th>Symbol</th><th>Type</th><th>Price</th><th>SL</th><th>TP</th><th>State</th></tr></table>
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
    const pl = d.float_pl||0;
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
      card('Alert delivery', d.channels&&!d.channels.gmail_cfg&&!d.channels.webhook
            ? 'LOCAL ONLY' : (d.channels&&d.channels.webhook?'webhook':'mail'),
           (d.channels&&(d.channels.gmail_cfg||d.channels.webhook))?'up':'flat')+
      card('Alerts queued', d.channels?d.channels.queued:'-');
    const a = d.access||{};
    const fw = a.firewall||{};
    document.getElementById('phone').innerHTML =
      '<span class="k">Phone / LAN</span><div class="v" style="font-size:14px;word-break:break-all">'
      + (a.phone_url ? '<a href="'+a.phone_url+'" style="color:#2ecc71">'+a.phone_url+'</a>'
                     : 'no LAN address right now (WiFi off?) — localhost still works')
      + '</div><div style="color:#7f8ea3;margin-top:4px">'
      + (fw.probed ? (fw.enabled ? 'macOS firewall <b>ON</b> — if the phone cannot load it, allow /usr/bin/python3 in Firewall, or use Tailscale' : 'macOS firewall off') : 'firewall state unknown')
      + (a.tailscale_ip ? ' · Tailscale <b>'+a.tailscale_ip+':'+a.port+'</b> (works away from home; tunnel currently stopped)' : '')
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
    const cp = document.getElementById('cpb');
    if (cp) cp.onclick = function(){ const u = (a.phone_url||'');
      if (navigator.clipboard) navigator.clipboard.writeText(u); cp.textContent = 'copied'; };
    const cb = document.getElementById('cmpb'); if (cb) cb.onclick = function(){ document.body.classList.toggle('cmp'); };
    tbl('pos', d.positions||[], p=>`<tr><td>${p.sym}</td><td>${p.action}</td><td>${p.vol}</td><td>${p.open}</td><td>${p.last}</td><td>${p.sl}</td><td>${p.tp}</td><td class="${p.profit>0?'up':(p.profit<0?'down':'')}">${p.profit}</td></tr>`);
    tbl('ord', d.orders||[], o=>`<tr><td>${o.sym}</td><td>${o.type}</td><td>${o.price}</td><td>${o.sl}</td><td>${o.tp}</td><td>${o.state}</td></tr>`);
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
document.getElementById('s').textContent='float '+(d.float_pl||0)+' USD · '+(d.positions||[]).length+' pos · '+(d.orders||[]).length+' orders · '+((d.record&&d.record.overall&&d.record.overall.line)||'win rate —')+' · sentry '+(d.sentry_alive?'LIVE':'DOWN');}catch(e){}}
t();setInterval(t,15000);</script></body></html>'''

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
        if path not in ("/", "/index.html", "/data.json", "/embed"):
            self.send_error(404)
            return
        if not is_local(client):
            import urllib.parse
            qs = urllib.parse.parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
            if qs.get("k", [""])[0] != security_key():
                return self._denied()      # exact compare, and an absent token lands here too
        if path.startswith("/data.json"):
            self._send(json.dumps(snapshot()), "application/json")
        elif path.startswith("/embed"):
            self._send(EMBED, "text/html")
        else:
            self._send(HTML, "text/html")

if __name__ == "__main__":
    threading.Thread(target=digest_loop, daemon=True).start()
    print(f"Trade Radar on 0.0.0.0:{PORT}", flush=True)
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
