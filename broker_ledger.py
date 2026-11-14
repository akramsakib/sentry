"""Shadow-ledger 'broker' — zero accounts. Same interface as broker.py (Alpaca).

Real prices (Coinbase public data, no key, works from any region GitHub runs in),
simulated fills in ledger.json. This is the v4.0 default: the bot earns its track
record against real candles; flipping config execution to 'alpaca' later adds a
real venue without touching the brain.

Fill model (conservative, MT5-flavored):
  buy limit   fills at limit price when ticker <= limit
  buy stop    fills at stop price when ticker >= stop
  protective sell stop: closes the position at stop price when ticker <= stop
  take-profit limit sells: closes at tp when ticker >= tp (handled by cycle enforce too)
"""
import json
import os
import time
import urllib.request

UA = {"User-Agent": "sentry-bot/4.0 (github-actions)"}


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER_F = os.path.join(HERE, "ledger.json")
COINBASE = "https://api.exchange.coinbase.com"

START_CASH = 100000.0


def _load():
    try:
        L = json.load(open(LEDGER_F))
    except Exception:
        L = {"cash": START_CASH, "realized": 0.0, "orders": [], "positions": []}
    for k, d in (("cash", START_CASH), ("realized", 0.0), ("orders", []), ("positions", [])):
        L.setdefault(k, d)
    # A hand-edited ledger.json once shipped "positions": {} and every cycle after the first
    # simulated fill died on dict.append. Coerce, don't crash: a bookkeeping file must never be
    # able to stop the bot.
    for k in ("orders", "positions"):
        if isinstance(L[k], dict):
            L[k] = list(L[k].values())
        elif not isinstance(L[k], list):
            L[k] = []
    return L


def _save(L):
    with open(LEDGER_F, "w") as f:
        json.dump(L, f, indent=1)


def _product(symbol):
    return symbol.replace("/", "-")  # BTC/USD -> BTC-USD


def _ticker_price(symbol):
    return float(_get(f"{COINBASE}/products/{_product(symbol)}/ticker", 15)["price"])


# ---------- data (Coinbase candles, closed-bar semantics like broker.crypto_bars) ----------

_GRAN = {"1Hour": 3600, "15Minute": 900, "1Day": 86400}


def crypto_bars(symbol, timeframe="1Hour", limit=200):
    g = _GRAN[timeframe]
    url = (f"{COINBASE}/products/{_product(symbol)}/candles"
           f"?granularity={g}&start={int(time.time()) - g * (limit + 2)}&end={int(time.time())}")
    rows = _get(url, 20)
    # Coinbase candles come back as [time, low, high, open, close, volume] (verified against the
    # live API 2026-11-14). Mapping them in the wrong order turns every candlestick pattern into
    # noise: with o=low/h=open/l=close/c=high, "bull" is always true and h-l is the body, not the
    # range — which is how C-H1 fired on five symbols at once with 0.04% stops. See test_data.py.
    out = [{"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(c[0])),
            "o": c[3], "h": c[2], "l": c[1], "c": c[4], "v": c[5]} for c in sorted(rows)]
    for b in out:  # never trust a provider's outliers: geometry must hold
        if not (b["h"] >= max(b["o"], b["c"]) >= min(b["o"], b["c"]) >= b["l"]):
            raise BrokerError(f"{symbol} {timeframe}: impossible bar {b}")
    if out and timeframe in _GRAN:
        out.pop()  # last candle is still forming -> closed bars only (matches broker.py)
    return out


# ---------- trading ----------

class BrokerError(Exception):
    pass


def _tick(L):
    """advance the simulation once: touch prices, match resting orders, enforce stops."""
    prices = {}
    for o in L["orders"]:
        if o["status"] != "open":
            continue
        sym = o["symbol"]
        try:
            prices[sym] = prices.get(sym) or _ticker_price(sym)
        except Exception:
            continue  # network wobble this cycle; next run retries
        px = prices[sym]
        if o["side"] == "buy":
            if o["type"] == "limit" and o.get("limit_price") and px <= o["limit_price"]:
                # Never worse than the market it walked into: a buy limit resting above the tape
                # fills at the touch, not at the limit. One number, used for the fill price, the
                # cash debit and the position basis — they disagreed once and the R-figures were
                # graded off a price nobody paid.
                fill = min(o["limit_price"], px)
                o["status"] = "filled"
                o["filled_avg_price"] = fill
                o["filled_qty"] = o["qty"]; o["filled_at"] = int(time.time())
                L["cash"] -= o["filled_qty"] * fill
                L["positions"].append({"symbol": sym, "qty": o["filled_qty"],
                                       "entry": fill, "cid": o["client_order_id"],
                                       "opened": int(time.time())})
            elif o["type"] == "stop" and o.get("stop_price") and px >= o["stop_price"]:
                o["status"] = "filled"; o["filled_avg_price"] = o["stop_price"]
                o["filled_qty"] = o["qty"]; o["filled_at"] = int(time.time())
                cost = o["filled_qty"] * o["stop_price"]
                L["cash"] -= cost
                L["positions"].append({"symbol": sym, "qty": o["filled_qty"],
                                        "entry": o["stop_price"], "cid": o["client_order_id"],
                                        "opened": int(time.time())})
        elif o["side"] == "sell" and o["type"] == "stop":
            pos = next((p for p in L["positions"] if p["symbol"] == sym), None)
            if pos and px <= o["stop_price"]:
                o["status"] = "canceled"
                _close_pos(L, pos, o["stop_price"])
        elif o["side"] == "sell" and o["type"] == "market":
            # the orchestrator's own stop/TP exit path sends a market close; without this the
            # shadow book opened positions it never closed, so realized P/L (and therefore the
            # accuracy loop that sizes the next trade) stayed at zero forever.
            pos = next((p for p in L["positions"] if p["symbol"] == sym), None)
            if pos:
                fill = px or pos["entry"]
                o["status"] = "filled"; o["filled_avg_price"] = fill
                o["filled_qty"] = pos["qty"]; o["filled_at"] = int(time.time())
                _close_pos(L, pos, fill)
    # refresh mark prices on held positions
    for p in L["positions"]:
        try:
            prices[p["symbol"]] = prices.get(p["symbol"]) or _ticker_price(p["symbol"])
            p["current_price"] = prices[p["symbol"]]
        except Exception:
            pass
    _save(L)


def _close_pos(L, pos, price):
    L["positions"].remove(pos)
    pnl = (price - pos["entry"]) * pos["qty"]
    L["cash"] += pos["qty"] * price
    L["realized"] += pnl


def account():
    L = _load()
    unreal = sum(p.get("current_price", p["entry"]) and (p.get("current_price", p["entry"]) - p["entry"]) * p["qty"]
                 for p in L["positions"])
    eq = L["cash"] + sum(p.get("current_price", p["entry"]) * p["qty"] for p in L["positions"])
    return {"cash": L["cash"], "equity": eq, "realized_pnl": L["realized"], "unrealized_pl": unreal,
            "mode": "shadow-ledger"}


def positions():
    _tick(_load())
    L = _load()
    return [{"symbol": p["symbol"], "qty": p["qty"], "avg_entry_price": p["entry"],
             "current_price": p.get("current_price", p["entry"])} for p in L["positions"]]


def open_orders():
    L = _load()
    return [{"id": o["id"], "client_order_id": o.get("client_order_id"), "symbol": o["symbol"],
             "side": o["side"], "type": o["type"], "status": "open",
             "limit_price": o.get("limit_price"), "stop_price": o.get("stop_price"),
             "qty": o["qty"]} for o in L["orders"] if o["status"] == "open"]


def order_by_cid(cid):
    L = _load()
    for o in reversed(L["orders"]):
        if o["client_order_id"] == cid:
            return dict(o)
    return None


def place_order(side, symbol, qty=None, notional=None, otype="limit", limit_price=None,
                stop_price=None, tif="gtc", cid=None):
    L = _load()
    if otype == "notional" or (notional is not None and qty is None):
        px = _ticker_price(symbol)
        qty = notional / px
    o = {"id": str(int(time.time() * 1000)), "client_order_id": cid or f"ledger{int(time.time()*1e3)%10**12}",
         "symbol": symbol, "side": side, "type": otype, "qty": qty,
         "limit_price": limit_price, "stop_price": stop_price, "status": "open",
         "placed_at": int(time.time())}
    L["orders"].append(o)
    _save(L)
    _tick(L)
    return dict(o)


def cancel_order(order_id):
    L = _load()
    for o in L["orders"]:
        if o["id"] == str(order_id) and o["status"] == "open":
            o["status"] = "canceled"
    _save(L)
    return {"ok": True}


def cancel_all():
    L = _load()
    for o in L["orders"]:
        if o["status"] == "open" and o["side"] == "buy":
            o["status"] = "canceled"  # keep protective sells; they're needed by _tick
    _save(L)
    return {"ok": True}
