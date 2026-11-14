#!/usr/bin/env python3
"""Coinbase Exchange adapter — real orders on a real book.

Implements the same functions `run_cycle.py` already calls on `broker`, so going live is one
config line:  "execution": "coinbase".   No SDK, no pip install — urllib + openssl only, and the
data path is the same host the shadow ledger reads, so paper and live numbers stay comparable.

Credentials (Actions Secrets; never in the repo, never printed):
  legacy key  COINBASE_API_KEY + COINBASE_API_SECRET + COINBASE_API_PASSPHRASE
  CDP  key    COINBASE_API_KEY + COINBASE_CDP_PEM        (ES256 JWT, signed with openssl)
  COINBASE_DRY=1        build and journal the exact payload, send nothing
  COINBASE_TEST=1       hit api.exchange.coinbase.com sandbox instead of production

Two things this file exists to get right, because both fail silently on Coinbase:
  * `client_oid` must be a lowercase UUIDv4 or the order is ACCEPTED BUT NEVER PROCESSED and
    disappears from all later REST calls. Sentry's internal cid is `<ms>n<seq>, so every cid is
    mapped to a deterministic UUIDv4 here (and mapped back), never sent raw.
  * price/size must land on the product's quote_increment / base_increment, and stop orders fire
    as LIMIT orders, so the trigger needs a limit price with slippage room or it triggers unfilled.
"""
import base64
import hashlib
from decimal import Decimal as D, ROUND_FLOOR
import hmac
import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

PROD = "https://api.exchange.coinbase.com"
BASE = os.environ.get("COINBASE_BASE") or (PROD if os.environ.get("COINBASE_TEST") != "1" else "https://api-public.sandbox.exchange.coinbase.com")
DRY = os.environ.get("COINBASE_DRY") == "1"      # builds payloads, reads nothing authenticated
UA = "sentry-bot/4.3"
GRAN = {"1Minute": 60, "5Minute": 300, "15Minute": 900, "1Hour": 3600, "6Hour": 21600, "1Day": 86400}
# how far outside the trigger the limit sits once a stop fires (0.15% covers normal tick-through)
SLACK = float(os.environ.get("COINBASE_SLACK", "0.0015"))
_OID_NS = uuid.UUID("6f1a2c34-0000-4000-8000-7c9d0e1f2a3b")   # fixed namespace: never change it


class BrokerError(Exception):
    pass


# ---------- ids ----------

def oid_for(cid):
    """Any internal cid -> deterministic lowercase UUIDv4. Same cid always gives the same uuid, so
    no mapping table has to survive between cycles (Actions runners are ephemeral)."""
    d = uuid.uuid5(_OID_NS, f"sentry:{cid}").hex
    return str(uuid.UUID("-".join((d[0:8], d[8:12], "4" + d[13:16], "8" + d[17:20], d[20:32]))))


# ---------- auth ----------

def _b64url(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _jwt_es256(signing_input, pem):
    with tempfile.TemporaryDirectory() as d:
        kf = os.path.join(d, "k.pem")
        with open(kf, "w") as f:
            f.write(pem if pem.strip().endswith("-----") else pem.replace("\\n", "\n"))
        os.chmod(kf, 0o600)
        sf = os.path.join(d, "s.der")
        p = subprocess.run(["openssl", "dgst", "-sha256", "-sign", kf, "-out", sf],
                           input=signing_input.encode(), capture_output=True)
        if p.returncode or not os.path.exists(sf):
            raise BrokerError(f"openssl sign failed: {p.stderr.decode()[:160]}")
        der = open(sf, "rb").read()
    if der[0] != 0x30 or der[2] != 0x02:
        raise BrokerError("unexpected ECDSA signature encoding")
    rl = der[3]
    r = der[4:4 + rl]
    i = 4 + rl
    if der[i] != 0x02:
        raise BrokerError("unexpected ECDSA signature (s)")
    sl = der[i + 1]
    s = der[i + 2:i + 2 + sl]
    return r.rjust(32, b"\0")[-32:] + s.rjust(32, b"\0")[-32:]      # JWS wants raw r||s, not DER


def _auth(method, path, body=b""):
    key = os.environ.get("COINBASE_API_KEY")
    sec = os.environ.get("COINBASE_API_SECRET")
    pass_ = os.environ.get("COINBASE_API_PASSPHRASE")
    pem = os.environ.get("COINBASE_CDP_PEM")
    if not key:
        raise BrokerError("no Coinbase credentials — set COINBASE_API_KEY (+ COINBASE_API_SECRET and "
                          "COINBASE_API_PASSPHRASE for a legacy key, or COINBASE_CDP_PEM for a CDP key)")
    if pem:
        ts = int(time.time())
        h = _b64url(json.dumps({"alg": "ES256", "typ": "JWT"}, separators=(",", ":")).encode())
        c = _b64url(json.dumps({"sub": key, "iss": "coinbase-app", "nbf": ts - 5, "exp": ts + 120,
                                "cnb": _b64url(hashlib.sha256(b"").digest())}, separators=(",", ":")).encode())
        tok = f"{h}.{c}.{_b64url(_jwt_es256(f'{h}.{c}', pem))}"
        return {"CB-ACCESS-KEY": key, "CB-ACCESS-SIGN": tok}
    if not (sec and pass_):
        raise BrokerError("legacy Coinbase key needs COINBASE_API_SECRET and COINBASE_API_PASSPHRASE")
    ts = str(int(time.time()))
    sig = hmac.new(sec.encode(), (ts + method + path).encode() + b"\n" + body, hashlib.sha256).hexdigest()
    return {"CB-ACCESS-KEY": key, "CB-ACCESS-SIGN": sig, "CB-ACCESS-TIMESTAMP": ts,
            "CB-ACCESS-PASSPHRASE": pass_}


def _req(method, path, params=None, body=None, tries=3, public=False):
    qs = ""
    if params:
        qs = "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    payload = b"" if body is None else json.dumps(body).encode()
    hdr = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": UA}
    if not public:
        hdr.update(_auth(method, path + qs, payload))
    last = None
    for attempt in range(tries):
        req = urllib.request.Request(BASE + path + qs, data=payload or None, method=method, headers=hdr)
        try:
            with urllib.request.urlopen(req, timeout=25) as r:
                txt = r.read().decode()
                return json.loads(txt) if txt.strip() else {}
        except urllib.error.HTTPError as e:
            txt = e.read().decode()[:300]
            last = f"{e.code} {txt}"
            if e.code in (408, 429, 500, 502, 503) and attempt < tries - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            if e.code in (400, 401, 403, 404, 422):       # never blind-retry an order request
                raise BrokerError(f"{method} {path}: {last}")
        except Exception as e:                            # noqa: BLE001 — network, not logic
            last = f"{type(e).__name__}: {e}"
            time.sleep(1.5 * (attempt + 1))
    raise BrokerError(f"{method} {path}: {last}")


# ---------- product metadata (increments are enforced strictly by the matching engine) ----------

_META = {}


def _product(symbol):
    return str(symbol).replace("/", "-").upper()


def _meta(symbol):
    pid = _product(symbol)
    if pid not in _META:
        d = _req("GET", f"/products/{pid}", public=True)
        _META[pid] = {"quote": str(d.get("quote_increment") or "0.01"),
                      "base": str(d.get("base_increment") or "0.00000001"),
                      "min_funds": float(d.get("min_market_funds") or 0),
                      "ok": d.get("status") == "online" and not d.get("trading_disabled")}
    return _META[pid]


def _dec(x):
    return D(str(x)) if isinstance(x, float) else D(x)


def _floor(v, inc):
    """Floor a Decimal to a multiple of inc. Decimal, not float: `int(0.94 / 0.01)` is 93, which
    would sell a whole tick early on every protective stop."""
    steps = (v / inc).to_integral_value(rounding=ROUND_FLOOR)
    return steps * inc


def _quant(x, increment):
    """Floor x to a multiple of increment, rendered with exactly the tick's decimals."""
    inc = str(increment)
    dp = len(inc.split(".")[1]) if "." in inc else 0
    if float(inc) <= 0:
        raise BrokerError(f"bad increment {increment}")
    return str(_floor(_dec(x), D(inc)).quantize(D(inc)))


def _px(symbol, price, up):
    """Price for a limit that fires off a trigger: at least one full tick beyond it, in the
    direction of travel. The 'at least one tick' matters — on a coarse-tick product a 0.15 % slack
    can be smaller than the tick itself and would land back on the trigger, producing an order
    that is accepted, triggers, then sits unfilled forever."""
    inc = D(str(_meta(symbol)["quote"]))
    trig = _dec(price)
    want = trig * (D(1) + D(str(SLACK)) if up else D(1) - D(str(SLACK)))
    step = max(abs(want - trig), inc)
    v = _floor(trig + step, inc) if up else _floor(trig - step, inc)
    if up and v <= trig:
        v = _floor(trig, inc) + inc
    if not up and v >= trig:
        v = _floor(trig, inc) - inc
    if v <= 0:
        raise BrokerError(f"{symbol}: no room for a protective stop below {price} at tick {inc}")
    return str(v.quantize(inc))


def _fmt(symbol, price):
    inc = str(_meta(symbol)["quote"])
    dp = len(inc.split(".")[1]) if "." in inc else 0
    return f"{float(price):.{dp}f}"


# ---------- market data (public, needs no key) ----------

def _bars(rows, now_ts=None):
    """[time, low, high, open, close, volume] -> our bar dicts. That column order is what broke
    the first port (reading open at index 1 made every bar "bullish" and stopped-out sizing went
    absurd), so it lives in one pure function the offline test can pin without a socket."""
    now_ts = now_ts or time.time()
    out = []
    for c in sorted(rows or [], key=lambda x: int(x[0])):
        b = {"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(c[0]))),
             "o": float(c[3]), "h": float(c[2]), "l": float(c[1]), "c": float(c[4]), "v": float(c[5])}
        if not (b["h"] >= max(b["o"], b["c"]) >= min(b["o"], b["c"]) >= b["l"]):
            raise BrokerError(f"candles: impossible bar {b}")
        out.append(b)
    if out and out[-1]["t"] > time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ts - 5)):
        out.pop()                                                     # still forming — never score it
    return out


def crypto_bars(symbol, timeframe="1Hour", limit=200):
    g = GRAN.get(timeframe, 3600)
    now = int(time.time())
    d = _req("GET", f"/products/{_product(symbol)}/candles",
             params={"granularity": g, "start": now - g * (limit + 2), "end": now}, public=True)
    return _bars(d, now)


def last_price(symbol):
    d = _req("GET", f"/products/{_product(symbol)}/ticker", public=True)
    return float(d["price"])


# ---------- account ----------

def account():
    if DRY:
        eq = float(os.environ.get("COINBASE_DRY_EQUITY") or 100000.0)   # rehearse any account size
        return {"equity": eq, "cash": eq, "crypto_value": 0.0}
    rows = _req("GET", "/accounts")
    usd = 0.0
    other = 0.0
    for a in rows if isinstance(rows, list) else []:
        try:
            av = float(a.get("available") or 0)
        except (TypeError, ValueError):
            continue
        cur = (a.get("currency") or "").upper()
        if cur in ("USD", "USDC"):
            usd += av
        elif av > 0:
            try:
                other += av * last_price(cur + "/USD")
            except (BrokerError, ValueError):
                pass
    return {"equity": round(usd + other, 2), "cash": round(usd, 2), "crypto_value": round(other, 2)}


def positions():
    """Spot has no position object: a position is a non-zero base-currency balance. run_cycle only
    needs symbol / qty / current_price from this; entry, SL and TP live in state.json."""
    if DRY:
        return []
    rows = _req("GET", "/accounts")
    out = []
    for a in rows if isinstance(rows, list) else []:
        try:
            av = float(a.get("available") or 0) + float(a.get("hold") or 0)
        except (TypeError, ValueError):
            continue
        cur = (a.get("currency") or "").upper()
        if av <= 0 or cur in ("USD", "USDC"):
            continue
        try:
            px = last_price(cur + "/USD")
        except BrokerError:
            px = 0.0
        out.append({"symbol": f"{cur}/USD", "qty": av, "current_price": px})
    return out


# ---------- orders ----------

def _norm(o):
    fs = float(o.get("filled_size") or 0)
    ev = float(o.get("executed_value") or 0)
    st = (o.get("status") or "").lower()
    if st in ("open", "pending", "received", "active", "placed"):
        st = "open"
    elif st in ("done", "filled", "settled"):
        st = "filled" if fs > 0 else "canceled"
    return {"id": o.get("id"), "client_order_id": o.get("client_oid"),
            "symbol": (o.get("product_id") or "").replace("-", "/"), "side": (o.get("side") or "").lower(),
            "type": (o.get("type") or "").lower(), "status": st,
            "qty": float(o.get("size") or 0), "filled_qty": fs,
            "filled_avg_price": round(ev / fs, 8) if fs and ev else (float(o.get("avg_fill_price")) if o.get("avg_fill_price") else None),
            "limit_price": float(o["price"]) if o.get("price") else None,
            "stop_price": float(o["stop_price"]) if o.get("stop_price") else None}


def open_orders(symbol=None):
    if DRY:
        return []
    rows = _req("GET", "/orders", params={"status": "open", "limit": 100,
                                         "product_id": _product(symbol) if symbol else None})
    return [_norm(o) for o in (rows if isinstance(rows, list) else [])]


def order_by_cid(cid):
    if DRY:
        return None
    try:
        o = _req("GET", f"/orders/client/{oid_for(cid)}")
        if isinstance(o, dict) and o.get("id"):
            return _norm(o)
    except BrokerError:
        pass
    for o in open_orders():
        if o.get("client_order_id") == oid_for(cid):
            return o
    return None


def fills(symbol=None, order_id=None):
    if DRY:
        return []
    rows = _req("GET", "/fills", params={"product_id": _product(symbol) if symbol else None,
                                        "order_id": order_id})
    return [{"price": float(f.get("price") or 0), "size": float(f.get("size") or 0),
             "side": f.get("side"), "order_id": f.get("order_id"), "time": f.get("time")}
            for f in (rows if isinstance(rows, list) else [])]


def place_order(side, symbol, qty=None, notional=None, otype="limit", limit_price=None,
                stop_price=None, tif="gtc", cid=None):
    """side: buy/sell · otype: market|limit|stop|stop_limit · cid: our internal id (never sent raw)."""
    side = "buy" if str(side).lower().startswith("b") else "sell"
    m = _meta(symbol)
    if not m["ok"]:
        raise BrokerError(f"{symbol} is not tradeable right now")
    ref = stop_price or limit_price or last_price(symbol)
    if qty is None:
        qty = float(notional or 0) / float(ref)
    qty = float(qty)
    if qty <= 0:
        raise BrokerError("zero or negative size")
    size = _quant(qty, m["base"])
    notional_ok = qty * float(ref) >= m["min_funds"]
    if not notional_ok:
        raise BrokerError(f"notional {qty * float(ref):.4f} below the {m['min_funds']} minimum for {symbol}")
    body = {"product_id": _product(symbol), "side": side, "size": size,
            "time_in_force": "GTC" if str(tif).lower().startswith("gtc") else str(tif).upper()}
    if cid:
        body["client_oid"] = oid_for(cid)
    if otype in ("market", "notional"):
        body["type"] = "market"
        body.pop("time_in_force")
        if side == "buy":
            body["funds"] = _quant(qty * float(ref), m["quote"])
            body.pop("size")
    elif otype == "limit":
        body["type"] = "limit"
        body["price"] = _quant(limit_price or ref, m["quote"])
    elif otype in ("stop", "stop_limit", "buy_stop_limit", "sell_stop_limit"):
        trig = float(stop_price or limit_price or ref)
        body["type"] = "stop_limit"
        body["stop"] = "entry" if side == "buy" else "loss"      # buy triggers at/above, sell at/below
        body["stop_price"] = _fmt(symbol, _quant(trig, m["quote"]))
        # A stop order executes as a LIMIT once triggered, so the limit must clear the trigger: equal
        # prices fill into a moving market and leave a "successful" order unfilled forever.
        body["price"] = _px(symbol, float(body["stop_price"]), side == "buy")
        if (side == "buy" and float(body["price"]) <= float(body["stop_price"])) or \
           (side == "sell" and float(body["price"]) >= float(body["stop_price"])):
            raise BrokerError(f"{symbol}: stop limit {body['price']} does not clear trigger {body['stop_price']}")
    else:
        raise BrokerError(f"unsupported order type: {otype}")
    if DRY:
        print(f"  DRY payload POST /orders {json.dumps(body)}")
        return {"id": f"dry{int(time.time() * 1000)}", "client_order_id": body.get("client_oid"),
                "symbol": symbol, "side": side, "type": otype, "qty": qty, "status": "open",
                "limit_price": float(body.get("price") or 0) or None,
                "stop_price": float(body.get("stop_price") or 0) or None, "payload": body}
    d = _req("POST", "/orders", body=body)
    if not isinstance(d, dict) or not d.get("id"):
        raise BrokerError(f"rejected: {str(d)[:200]}")
    o = _norm(d)
    o["payload"] = body
    return o


def cancel_order(order_id):
    if DRY:
        return {"cancelled": True, "id": order_id, "dry": True}
    _req("DELETE", f"/orders/{order_id}")
    return {"cancelled": True, "id": order_id}


def cancel_all(symbol=None):
    ids = [o["id"] for o in open_orders(symbol) if o.get("id")]
    if not ids:
        return {"cancelled": 0}
    if DRY:
        return {"cancelled": len(ids), "dry": True}
    _req("POST", "/orders/batch_cancel", body={"order_ids": ids})
    return {"cancelled": len(ids)}


def verify():
    """Read-only proof of life. Places nothing."""
    a = account()
    print(f"  auth ok · cash ${a['cash']:,.2f} · equity ${a['equity']:,.2f} · "
          f"{len(open_orders())} resting orders · {len(positions())} positions · "
          f"SOL {last_price('SOL/USD')}")
    p = _meta("SOL/USD")
    print(f"  sol/USD tradable={p['ok']} tick={p['quote']} step={p['base']} min_notional={p['min_funds']}")
    print(f"  cid->oid: 1794662610992n5 -> {oid_for('1794662610992n5')} (stable: "
          f"{oid_for('1794662610992n5') == oid_for('1794662610992n5')})")


if __name__ == "__main__":
    try:
        verify()
    except BrokerError as e:
        print(f"  FAILED: {e}")
        raise SystemExit(1)
