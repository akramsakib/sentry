#!/bin/bash
# account_switch.sh -- safely move the Sentry build between MT5 accounts.
#
# Why this exists: the terminal's MCP server exposes no account-creation tool
# (checked: the full tools/list has trading/chart/journal/tester/alert tools only),
# so the demo registration itself must be done by a human in the MT5 dialog.
# Everything AROUND that step is scriptable, and that is what this does:
#
#   status    read-only: which account is logged in, what the resident's book holds
#   verify    read-only: full account_info from the terminal + a match against state.json
#   pause     entries_enabled=false (backs up the file) -- no order can be sent
#   resume    restore the backed-up desk_mode.json
#   snapshot  copy state.json / trades_log.jsonl / journal / desk_mode.json into archive/
#   fresh     start a clean book for the newly-logged-in account (archive first, revert-able)
#   revert    put the archived state.json + trades_log.jsonl back exactly as they were
#
# Nothing here touches money: every account this build can reach is a demo account,
# and no crypto venue key exists on this machine.

set -u
D="$HOME/hermes_sentry"
MODE="$D/desk_mode.json"
STATE="$D/state.json"
LOG="$D/trades_log.jsonl"
JRN="$D/sentry_journal.md"
JOB="com.hermes.sentry"
MT="$HOME/Library/Application Support/net.metaquotes.wine.metatrader5/drive_c/Program Files/MetaTrader 5"
TS="$(date +%Y%m%d-%H%M%S)"
ARC="$D/archive"
STAMPF="$ARC/.switch-stamp"

fail() { echo "ABORT: $*" >&2; exit 1; }
[ -d "$D" ] || fail "$D not found -- this runs on the Mac that hosts the resident"

# ---------------------------------------------------------------- terminal MCP
mcp() { # mcp <tool> <args-json>  -> raw JSON-RPC response on stdout
  local U="http://127.0.0.1:22346/mcp"
  local K
  K="$(iconv -f UTF-16LE -t UTF-8 "$MT/config/assistant.ini" 2>/dev/null | tr -d '\r' \
       | grep -m1 -o 'ApiKey=[A-Za-z0-9]*' | cut -d= -f2)"
  [ -n "$K" ] || { echo "" ; return 1; }
  local H=(-H "Content-Type: application/json" -H "Accept: application/json, text/event-stream"
           -H "MCP-Protocol-Version: 2025-06-18" -H "Authorization: Bearer $K")
  local hd="/tmp/.acctsw.$$"
  curl -sS --compressed -D "$hd" -o /dev/null --max-time 25 -X POST "$U" "${H[@]}" \
    -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"account_switch","version":"1"}}}' || { rm -f "$hd"; return 1; }
  local sid
  sid="$(grep -iE '^mcp-session-id:' "$hd" | tr -d '\r' | awk '{print $2}')"
  rm -f "$hd"
  [ -n "$sid" ] || return 1
  curl -sS --compressed -o /dev/null --max-time 25 -X POST "$U" "${H[@]}" -H "Mcp-Session-Id: $sid" \
    -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'
  curl -sS --compressed --max-time 40 -X POST "$U" "${H[@]}" -H "Mcp-Session-Id: $sid" \
    -d "{\"jsonrpc\":\"2.0\",\"id\":7,\"method\":\"tools/call\",\"params\":{\"name\":\"$1\",\"arguments\":$2}}" \
    | sed 's/^data: //'
}

acct() { # print "login|server|type|balance|equity|profit" from the terminal, or empty
  mcp get_trading_account_info '{}' 2>/dev/null | /usr/bin/python3 -c '
import sys, json
try:
    a = json.loads(json.load(sys.stdin)["result"]["content"][0]["text"])["account"]
    print("%s|%s|%s|%s|%s|%s" % (a.get("login"), a.get("server"), a.get("type"),
                                 a.get("balance"), a.get("equity"), a.get("profit")))
except Exception:
    pass'
}

describe() {
  local a; a="$(acct)"
  if [ -z "$a" ]; then
    echo "  terminal: NOT REACHABLE on 127.0.0.1:22346 (MT5 down, or MCP off in Tools>Options>Expert)"
  else
    IFS='|' read -r ln sv ty bal eq pf <<<"$a"
    echo "  terminal login : $ln   server $sv   type: $ty"
    echo "  balance/equity : $bal / $eq      floating profit: $pf"
    case "$ty" in demo) echo "  money at risk  : NONE -- this is a demo account";;
                 real) echo "  *** type=real: REAL MONEY. Stop and think before pausing/switching. ***";;
                 *)    echo "  money at risk  : unknown ('"$ty"') -- check before arming";; esac
  fi
  /usr/bin/python3 - "$STATE" "$LOG" <<'PY'
import json, os, sys
sp, lp = sys.argv[1], sys.argv[2]
try:
    s = json.load(open(sp))
except Exception:
    print("  resident state : none yet (fresh start is safe -- load_state tolerates it)"); s = {}
if s:
    print("  resident day   : %s   watch_asof %s" % (s.get("day"), s.get("watch_asof")))
    print("  book           : %d rows | orders today %d | positions open %s | floating %s"
          % (len(s.get("book") or []), len(s.get("orders") or []),
             s.get("positions_open"), s.get("positions_total_pl")))
    lr = s.get("live_record") or {}
    if lr:
        # v4.7.9: the resident grades its OWN sent trades off the terminal's closed positions. Quote its
        # numbers rather than re-deriving them, and never call an open trade a result.
        print("  live record    : sent %s | graded %s (%sW/%sL) | net %+.2fR | %+.2f %s | ungraded %s"
              % (lr.get("sent"), lr.get("graded"), lr.get("wins"), lr.get("losses"),
                 lr.get("net_r") or 0.0, lr.get("net_usd") or 0.0,
                 lr.get("currency") or "ccy unknown", lr.get("ungraded")))
        if lr.get("graded"):
            print("  grading        : %s of %s matched from the terminal's closes; a sent trade with no close "
                  "is left ungraded, which is the honest state" % (lr.get("from_terminal"), lr.get("graded")))
    else:
        print('  grading        : this build predates the close-join (no live_record in state.json) '
              '-- the win rate below is the PAPER track only')
    sg = s.get("sizing") or {}
    if sg:
        print("  sizing         : guard %s, %s of equity | capped today %s | refused %s"
              % ("on" if sg.get("guard_on") else "OFF",
                 ("%s%%" % round(100 * sg.get("max_frac", 0))) if sg.get("max_frac") else "no ceiling",
                 sg.get("capped_today"), sg.get("refused_today") or "{}"))
try:
    rows = [json.loads(x) for x in open(lp, errors="replace") if x.strip()]
    g = [r for r in rows if r.get("result") in ("win", "loss")]
    f = [r for r in rows if r.get("fired")]
    gf = [r for r in f if r.get("result") in ("win", "loss")]
    print("  trades_log     : %d rows | sent %d (graded %d) | paper graded %d | net R live %+.2f / paper %+.2f"
          % (len(rows), len(f), len(gf), len([r for r in g if not r.get("fired")]),
             sum(r.get("R") or 0 for r in gf), sum(r.get("R") or 0 for r in g if not r.get("fired"))))
    if len(gf) < len(f) and not (s.get("live_record") or {}):
        print("  NOTE           : %d of %d sent trades carry no grade. On a pre-v4.7.9 build the cause is "
              "known: the send reply was truncated at 300 bytes, so no ticket was ever captured and nothing "
              "could be joined. The current build captures the id and grades from the terminal's own closes."
              % (len(f) - len(gf), len(f)))
except Exception as e:
    print("  trades_log     : unreadable (%s)" % e)
try:
    m = json.load(open(os.path.join(os.path.dirname(sp), "desk_mode.json")))
    print("  entries_enabled: %r" % m.get("entries_enabled"))
except Exception as e:
    print("  entries_enabled: unknown (%s) -- send_order treats a missing file as OFF" % e)
PY
}

# ---------------------------------------------------------------- commands
case "${1:-status}" in
  status)
    echo "== account switch kit -- current state =="; describe; exit 0 ;;

  verify)
    echo "== verify: what the terminal says, and what the desk is showing =="
    mcp get_trading_account_info '{}' | /usr/bin/python3 -c '
import sys, json
d = json.loads(json.load(sys.stdin)["result"]["content"][0]["text"])
a, t = d["account"], d.get("terminal", {})
print("  login %s | %s | %s | %s" % (a.get("login"), a.get("server"), a.get("broker"), a.get("type")))
print("  balance %.2f  equity %.2f  margin %.2f  free %.2f  floating %.2f  %s"
      % (a.get("balance") or 0, a.get("equity") or 0, a.get("margin") or 0,
         a.get("margin_free") or 0, a.get("profit") or 0, a.get("currency")))
print("  read_only=%s  margin_mode=%s  commissions=%s  swaps=%s"
      % (a.get("read_only"), a.get("margin_mode"), a.get("commissions"), a.get("swaps")))
c = t.get("connection", {})
print("  terminal: build %s  connection %s  authorized %s"
      % (t.get("build"), c.get("state"), c.get("last_authorized_at")))' || fail "MCP unreachable"
    mcp get_trading_open_positions '{}' | /usr/bin/python3 -c '
import sys, json
d = json.loads(json.load(sys.stdin)["result"]["content"][0]["text"])
for k in ("positions", "orders"):
    rows = [r for r in (d.get(k) or []) if isinstance(r, dict)]
    print("  live %-9s: %d" % (k, len(rows)))
    for r in rows[:12]:
        print("      %-9s %-11s vol %-7s @%-10s sl %-10s tp %-10s %r"
              % (r.get("symbol"), r.get("type"), r.get("volume_initial") or r.get("open_volume"),
                 r.get("price_order") or r.get("open_price"), r.get("stop_loss"), r.get("take_profit"),
                 r.get("comment")))'
    describe
    exit 0 ;;

  pause)
    [ -f "$MODE" ] || fail "no $MODE -- refusing to guess the current mode"
    mkdir -p "$ARC"; cp -p "$MODE" "$ARC/desk_mode.$TS.json"
    # The stamp is what makes `resume` able to find this exact backup again.
    echo "$TS" > "$STAMPF"
    # The journal is append-only evidence and there is no other copy of it anywhere, so
    # snapshot it before any experiment runs against the live build. Learned the hard way.
    [ -f "$JRN" ] && cp -p "$JRN" "$ARC/journal.$TS.md" \
      && echo "journal snapshot: $ARC/journal.$TS.md ($(wc -l < "$JRN") lines) -- restore with:"
    [ -f "$ARC/journal.$TS.md" ] && echo "  cp -p $ARC/journal.$TS.md $JRN"
    printf '{ "entries_enabled": false, "paused_by": "account_switch.sh", "paused_at": "%s" }\n' "$TS" > "$MODE"
    echo "entries are OFF (backup: $ARC/desk_mode.$TS.json). The resident still watches and journals;"
    echo "it just logs each setup as CANDIDATE ... awaiting Arena desk decision instead of sending."
    ;;

  resume)
    # Prefer the stamp; if it is missing (an older build of this kit, or a wiped archive
    # marker), fall back to the most recent desk_mode backup. Either way we restore a
    # file the terminal actually had, never a value we invented.
    LAST=""
    [ -f "$STAMPF" ] && LAST="$(cat "$STAMPF")"
    if [ -z "$LAST" ] || [ ! -f "$ARC/desk_mode.$LAST.json" ]; then
      LAST="$(ls -t "$ARC" 2>/dev/null | grep -oE 'desk_mode\.[0-9-]+\.json' | head -1 \
              | sed -e 's/^desk_mode\.//' -e 's/\.json$//')"
      [ -n "$LAST" ] && echo "  (no stamp -- using the newest backup: desk_mode.$LAST.json)"
    fi
    [ -n "$LAST" ] && [ -f "$ARC/desk_mode.$LAST.json" ] || fail "no desk_mode backup to restore from -- set desk_mode.json by hand"
    cp -p "$ARC/desk_mode.$LAST.json" "$MODE"
    echo "desk_mode.json restored from the $LAST backup:"; cat "$MODE"
    ;;

  snapshot)
    mkdir -p "$ARC/pre-$TS"
    for f in state.json trades_log.jsonl sentry_journal.md desk_mode.json; do
      [ -f "$D/$f" ] && cp -p "$D/$f" "$ARC/pre-$TS/$f" && echo "  archived $f"
    done
    mcp get_trading_account_info '{}' > "$ARC/pre-$TS/account.json" 2>/dev/null \
      && echo "  archived the terminal's own account_info (which account this snapshot belongs to)"
    echo "$TS" > "$STAMPF"
    echo "snapshot: $ARC/pre-$TS"
    ;;

  fresh)
    [ -f "$STAMPF" ] || { mkdir -p "$ARC"; }
    S2="$TS"; mkdir -p "$ARC/pre-$S2"
    for f in state.json trades_log.jsonl sentry_journal.md desk_mode.json; do
      [ -f "$D/$f" ] && mv -f "$D/$f" "$ARC/pre-$S2/$f" && echo "  moved $f -> archive/pre-$S2/"
    done
    mcp get_trading_account_info '{}' > "$ARC/pre-$S2/account.json" 2>/dev/null
    echo "$S2" > "$STAMPF"
    printf '{ "entries_enabled": false, "paused_by": "account_switch.sh fresh", "paused_at": "%s" }\n' "$S2" > "$MODE"
    echo "$S2" > "$ARC/.book-opened"
    # The resident recreates state.json from nothing (load_state: except -> {}), and
    # skill_acc returns a neutral 0.5 with no log, so self_size starts at base risk.
    if launchctl list 2>/dev/null | grep -q "$JOB"; then
      launchctl kickstart -k "gui/$(id -u)/$JOB" >/dev/null 2>&1 \
        && echo "  resident restarted with an empty book; entries stay OFF until you say resume"
    fi
    sleep 3
    echo; echo "== new book =="; describe
    ;;

  revert)
    [ -f "$STAMPF" ] || fail "nothing to revert"
    LAST="$(cat "$STAMPF")"; A="$ARC/pre-$LAST"
    [ -d "$A" ] || fail "$A missing"
    for f in state.json trades_log.jsonl sentry_journal.md desk_mode.json; do
      [ -f "$A/$f" ] && cp -p "$A/$f" "$D/$f" && echo "  restored $f"
    done
    if launchctl list 2>/dev/null | grep -q "$JOB"; then
      launchctl kickstart -k "gui/$(id -u)/$JOB" >/dev/null 2>&1 && echo "  resident restarted on the restored book"
    fi
    echo "revert copied from $A (the archive is untouched, so this is repeatable)"
    ;;

  handoff)
    cat <<'TXT'
What only a human can do, and what to copy out of it
-----------------------------------------------------
The MT5 terminal exposes no account-creation tool over its MCP interface, and the
registration form is a Wine-rendered web view with no scriptable controls, so the
demo itself must be clicked by hand -- in the terminal or on the phone.

Terminal:  File > Open an Account > search "MetaQuotes" > MetaQuotes-Demo
           > Create a demo account, then fill:
             First / Last name : yours
             Email             : the address you want the credentials sent to
             Phone             : international format, e.g. +60183560937
             Account type      : Demo          Currency: USD
             Deposit           : 50            Leverage: 1:100 (see the caveat below)
             Hedge mode        : on (this build assumes hedging; netting changes its maths)

Read the confirmation dialog BEFORE closing it and copy all three lines:
    Login (account number)      ____
    Master password             ____   <- the one that can trade; needed on the phone
    Investor password           ____   <- read-only; safe to share, fine for watching
and note the server name: MetaQuotes-Demo.
MT5 stores the password in an encrypted accounts.dat, so this is the only moment
the master password is visible. Nothing can recover it afterwards.

Phone (iOS/Android MT5):  Settings (or the app's start screen) > "+" / New account
           > My existing account > search the server "MetaQuotes-Demo"
           > Login + Investor password (use Master password if you want it to trade).
           Do NOT pick "MetaQuotes-Demo" from a broker list that is not the same server
           the desktop created the account on -- the number will not be found.

Deposit caveat: the MetaQuotes demo dialog accepts a deposit amount, but its minimum
is set by the demo server, not by us, and third-party guides commonly describe presets
of 10,000 / 50,000 / 100,000 USD. If 50 is refused, use 100 and say so -- the whole
point of this experiment is a base so small that the broker's 0.01-lot minimum is the
binding constraint, and that is still true at 100 (it just halves the per-trade risk
percentage from ~7% to ~3.5%).
TXT
    ;;

  *)  sed -n '2,20p' "$0"; exit 2 ;;
esac
