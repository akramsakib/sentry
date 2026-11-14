"""Alpaca paper-trading client — stdlib only (no pip deps to break in CI).

Data: https://data.alpaca.markets  (crypto bars 24/7)
Trade: https://paper-api.alpaca.markets
Keys come from env ALPACA_KEY_ID / ALPACA_SECRET (repo Secrets).
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

DATA = "https://data.alpaca.markets"
TRADE = os.environ.get("ALPACA_BASE") or "https://paper-api.alpaca.markets"


class BrokerError(Exception):
    pass


def _req(base, path, method="GET", params=None, body=None):
    url = base + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method=method)
    req.add_header("APCA-API-KEY-ID", os.environ.get("ALPACA_KEY_ID", ""))
    req.add_header("APCA-API-SECRET-KEY", os.environ.get("ALPACA_SECRET", ""))
    if body is not None:
        req.add_header("Content-Type", "application/json")
        data = json.dumps(body).encode()
    else:
        data = None
    try:
        with urllib.request.urlopen(req, data, timeout=25) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raise BrokerError(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:300]}") from e
    except Exception as e:  # network/timeout — caller escalates loudly
        raise BrokerError(f"{method} {path} -> {e!r}") from e


# ---------- market data ----------

def crypto_bars(symbol, timeframe="1Hour", limit=200):
    """symbol e.g. 'BTC/USD'. Returns list of closed-bar dicts {t,o,h,l,c,v} oldest→newest."""
    d = _req(DATA, "/v1beta3/crypto/us/bars", params={
        "symbols": symbol, "timeframe": timeframe, "limit": limit, "adjustment": "raw"})
    bars = (d.get("bars") or {}).get(symbol) or []
    out = [{"t": b["t"], "o": float(b["o"]), "h": float(b["h"]),
            "l": float(b["l"]), "c": float(b["c"]), "v": float(b.get("v", 0))} for b in bars]
    if out:
        out.pop()  # last bar is the still-open candle → closed bars only
    return out


# ---------- trading ----------

def account():
    return _req(TRADE, "/v2/account")

def positions():
    return _req(TRADE, "/v2/positions") or []

def open_orders():
    return _req(TRADE, "/v2/orders", params={"status": "open", "limit": 200}) or []

def order_by_cid(cid):
    try:
        return _req(TRADE, f"/v2/orders/by_client_id/{cid}")
    except BrokerError as e:
        if "404" in str(e):
            return None
        raise

def place_order(side, symbol, qty=None, notional=None, otype="limit", limit_price=None, stop_price=None, tif="gtc", cid=None):
    body = {"symbol": symbol, "side": side, "type": otype, "time_in_force": tif}
    if qty is not None:
        body["qty"] = round(qty, 8)
    elif notional is not None:
        body["notional"] = round(float(notional), 2)
    if limit_price is not None:
        body["limit_price"] = round(float(limit_price), 8)
    if stop_price is not None:
        body["stop_price"] = round(float(stop_price), 8)
    if cid:
        body["client_order_id"] = cid
    return _req(TRADE, "/v2/orders", method="POST", body=body)

def cancel_order(order_id):
    return _req(TRADE, f"/v2/orders/{order_id}", method="DELETE")

def cancel_all():
    return _req(TRADE, "/v2/orders", method="DELETE")
