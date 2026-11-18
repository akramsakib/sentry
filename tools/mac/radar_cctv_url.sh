#!/bin/bash
# radar_cctv_url.sh -- print the address your PHONE should open, with the token it needs.
#
# Two routes exist and only one of them works away from the house:
#   LAN       same WiFi as the Mac  ->  http://<mac-lan-ip>:8790/cctv?k=<token>
#   tailnet   anywhere, VPN-grade   ->  http://<100.x.y.z>:8790/cctv?k=<token>   (needs Tailscale running)
#
# There is deliberately NO public route: the recorder's own login stays in ~/hermes_sentry/cctv.json (600)
# and never reaches the browser, and the phone is handed a proxied tile instead. Turning this into a public
# URL would put an 8-camera CCTV feed on the open internet behind one 11-character token.
#
# Usage:
#   ./radar_cctv_url.sh                 show the URL(s), the QR-free way, for you to open
#   ./radar_cctv_url.sh --rotate        issue a NEW token first (do this if the old one was ever exposed)
#   ./radar_cctv_url.sh --start-ts      start Tailscale if it is installed but stopped, then report
#   ./radar_cctv_url.sh --check         test the routes from here and say which one answers
set -euo pipefail
cd "$(dirname "$0")"

KEY_F="$HOME/hermes_sentry/radar.key"
[ -f "$KEY_F" ] || KEY_F="$HOME/hermes_sentry/sentry_state/radar.key"
PORT=8790
MODE="${1:-show}"

rotate() {
  k=$(python3 -c "import secrets;print(secrets.token_urlsafe(8))")
  ( umask 077; printf '%s\n' "$k" > "$KEY_F" )
  chmod 600 "$KEY_F"
  echo "new token written to $KEY_F (600). The radar reads it on its next start:"
  echo "  launchctl kickstart -k gui/\$(id -u)/com.hermes.radar"
  echo "The OLD token stops working at that moment, which is the point of rotating."
  KEY="$k"
}

lan_ip() {
  for i in en0 en1 en2; do
    a=$(ipconfig getifaddr "$i" 2>/dev/null || true)
    [ -n "$a" ] && { echo "$a"; return; }
  done
  ifconfig 2>/dev/null | awk '/inet (192\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.)/{print $2; exit}'
}

ts_ip() {
  /usr/local/bin/tailscale ip -4 2>/dev/null | head -1 || \
  "$HOME/Applications/Tailscale.app/Contents/MacOS/Tailscale" ip -4 2>/dev/null | head -1 || true
}

[ -n "${KEY:-}" ] || KEY=$(cat "$KEY_F" 2>/dev/null | tr -d '\n' || echo "")
L=$(lan_ip || true); T=$(ts_ip || true)

case "$MODE" in
  --rotate) rotate ;;
  --start-ts)
    if [ -z "$T" ]; then
      echo "starting Tailscale (needs your admin password; this is the ONLY step I cannot do for you)..."
      sudo launchctl load -w /Library/LaunchDaemons/com.tailscale.ipn.macsys.plist 2>/dev/null || true
      /usr/local/bin/tailscale up 2>&1 | head -3
      sleep 6; T=$(ts_ip || true)
    fi
    [ -n "$T" ] && echo "tailnet address: $T" || echo "still stopped -- open the Tailscale menu-bar icon and Connect"
    ;;
  --check)
    for base in "$L" "$T"; do
      [ -n "$base" ] || continue
      code=$(curl -s -m 8 -o /dev/null -w '%{http_code}' "http://$base:$PORT/cctv?k=$KEY" || echo ERR)
      notok=$(curl -s -m 8 -o /dev/null -w '%{http_code}' "http://$base:$PORT/cctv" || echo ERR)
      echo "  $base -> with token: $code   without: $notok (want 200 / 403)"
    done
    st=$(/usr/local/bin/tailscale status -json 2>/dev/null | python3 -c "import json,sys
try: print(json.load(sys.stdin).get('BackendState'))
except Exception: print('unknown')" 2>/dev/null || echo unknown)
    echo "  tailscale backend: $st"
    python3 - <<'PY' 2>/dev/null || true
import json
d = json.load(open("/Users/sakib/hermes_sentry/cctv.json"))
print("  recorder login present in cctv.json:", "YES" if d.get("password") else "NO -- tiles will show 503 until it is filled in")
PY
    ;;
  *)
    echo "On the same WiFi as the Mac (works now, no setup):"
    [ -n "$L" ] && echo "    http://$L:$PORT/cctv?k=$KEY" || echo "    (no LAN address found -- is the Mac on WiFi?)"
    echo
    echo "From anywhere (phone on mobile data, or you are out):"
    if [ -n "$T" ]; then
      echo "    http://$T:$PORT/cctv?k=$KEY"
      echo "    (Tailscale address; your phone must be on the same tailnet)"
    else
      echo "    Tailscale is installed but stopped on the Mac, so there is no tailnet address yet."
      echo "    Run:  $0 --start-ts      then re-run this to see the URL"
    fi
    echo
    echo "The token is required on every address that is not the Mac itself; localhost needs none."
    echo "If this screen was photographed, shared, or pasted anywhere: $0 --rotate"
    ;;
esac
