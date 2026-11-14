#!/usr/bin/env python3
"""Bitget adapter — USDT-M perpetuals on the venue the user ALREADY has (verified, 2026-11-14).

Why this file exists, in one sentence: OKX was chosen from this runner because Bybit and Binance
refuse a US data-centre IP (HTTP 451 / CloudFront 403), and an adapter nobody can poke is an
adapter nobody can ship. Bitget answers here — market data 200, private endpoints 40006
"Invalid ACCESS_KEY" (path live, key absent) — so its payloads can be built, checked and pinned
offline and then proven from the user's own Mac, which reaches all four venues.

Cost, read from the venue's own `/api/v2/mix/market/contracts` (not from a help page): BTC/ETH/
XRP/SOL/DOGE/ADA/LINK/LTC/BCH/AVAX perps all publish **0.02 % maker / 0.06 % taker** at the base
tier. This playbook risks 1R through ~0.5 % stops, so taker both ways costs 0.24R (0.16R if the
entry leg fills as a maker) — inside the
0.25R live guard (`live_max_fee_r`), which is the only reason a venue is interesting here at all.
`python3 broker_bitget.py fees` re-reads that schedule and prints what every symbol actually pays.

Interface matches what `run_cycle.py` calls on `broker`, so the venue is one config line:
"execution": "bitget". Perps mean shorts are real (CAN_SHORT) and both protective legs ride on the
entry order (ATTACH_TP_SL) — the venue enforces them while this runner sleeps.

Credentials (env only; never printed, never committed):
  BITGET_API_KEY, BITGET_API_SECRET, BITGET_API_PASSPHRASE
  BITGET_MARGIN   "isolated" (default; Bitget's own default) or "crossed"
  BITGET_DRY=1    build and journal the exact payload, send nothing
  BITGET_DRY_EQUITY   pretend-wallet size for a dry rehearsal
  BITGET_SIM=1  + BITGET_SIM_BASE   point at a testnet/demo host if the account has one
  BITGET_PASS_CODE    if the account set a fund password, it is required on money endpoints

Three things this file gets deliberately right, because Bitget differs from OKX on all three:
  * SIZES ARE COINS, NOT CONTRACTS. There is no ctVal multiplier: `size` is the base-coin amount,
    rounded to `volumePlace` decimals. A port that reuses OKX's contract maths silently trades the
    wrong size — the whole point of `minTradeNum` is that it must never be below the venue's floor.
  * A TRIGGERED ENTRY IS NOT A SEPARATE ENDPOINT. `place-order` takes `orderType=limit` plus
    `triggerType=fill_price` + `triggerPrice` (and `executePrice` for the collar). OKX needs
    /trade/order-algo; copying that shape here is a 40017, not a wrong fill.
  * ONE-WAY POSITION MODE by default: `side=buy|sell` and NO `tradeSide`. Adding tradeSide to a
    one-way account is rejected. `hedge` support is explicit below (BITGET_HEDGE=1) and untested
    without a key, so the bot states which mode it assumed in every journal line.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal as D, ROUND_FLOOR, ROUND_CEILING

HOST = os.environ.get("BITGET_BASE") or ("https://" + os.environ["BITGET_SIM_BASE"].strip("/ ")
                                         if os.environ.get("BITGET_SIM") == "1" and os.environ.get("BITGET_SIM_BASE")
                                         else "https://api.bitget.com")
DRY = os.environ.get("BITGET_DRY") == "1"
SIM = os.environ.get("BITGET_SIM") == "1"
PRODUCT = os.environ.get("BITGET_PRODUCT") or "usdt-futures"
MARGIN = (os.environ.get("BITGET_MARGIN") or "isolated").lower()
MARGIN_COIN = os.environ.get("BITGET_MARGIN_COIN") or "USDT"
HEDGE = os.environ.get("BITGET_HEDGE") == "1"
CAN_SHORT = True                      # perps: a sell opens a short in one-way mode
ATTACH_TP_SL = True                   # presetStopSurplusPrice / presetStopLossPrice ride the entry
UA = "sentry-bot/4.7"
# Bitget's k-line names are mixed-case and BOTH spellings exist, but not on both endpoints:
# /market/candles takes 1Hutc/4Hutc/1Dutc, /market/history-candles refuses them (400171) and takes
# 1H/4H/1D. Crypto bars are already UTC-aligned on either, so this adapter uses ONE endpoint —
# history-candles, which returns CLOSED bars only (no forming-candle trap, no confirm flag to read)
# — and the names below are that endpoint's list. An adapter that "worked" on /candles names would
# fail the very first fetch: it did exactly that on 2026-11-14, and failed LOUD, which is the point.
BAR = {"1Minute": "1m", "3Minute": "3m", "5Minute": "5m", "15Minute": "15m", "30Minute": "30m",
       "1Hour": "1H", "4Hour": "4H", "6Hour": "6H", "12Hour": "12H",
       "1Day": "1D", "1Week": "1W", "1Month": "1M"}
GRANULARITY_OK = set(BAR.values())
SLACK = float(os.environ.get("BITGET_SLACK") or "0.0015")    # limit clearance past a trigger


class BrokerError(Exception):
    pass


# ---------- ids ----------
# Sentry's cid is `sentry{SYM}{ms}n{seq}` (up to 60 chars); Bitget's clientOid is alnum/dash/underscore
# and shorter, so every cid folds to a deterministic 32-char id — same cid, same id, forever, no
# mapping table that has to survive between runs. Losing this mapping is how an order becomes invisible.
def oid_for(cid):
    return "sen" + hashlib.sha1(f"bitget:{cid}".encode()).hexdigest()[:29]


# ---------- symbols & increments ----------
def _sym(symbol):
    """'BTC/USD' (the config's symbol) -> 'BTCUSDT' (Bitget's instrument)."""
    base = str(symbol).split("/")[0].upper()
    return f"{base}USDT"


_META = {}


def _meta(symbol):
    """Price/size increments straight from the venue. `pricePlace` decimals = tick, `volumePlace`
    decimals = the size step, `minTradeNum` the floor, and the fee row comes along for the ride."""
    s = _sym(symbol)
    if s not in _META:
        d = _req("GET", "/api/v2/mix/market/contracts", params={"symbol": s, "productType": PRODUCT},
                 public=True)
        rows = d.get("data") or []
        if not rows:
            raise BrokerError(f"{s}: not listed on Bitget {PRODUCT}")
        i = rows[0]
        pp, vp = int(i.get("pricePlace") or 2), int(i.get("volumePlace") or 2)
        _META[s] = {"tick": "1e-%d" % pp if pp < 28 else "0.01", "lot": "1e-%d" % vp if vp < 28 else "0.01",
                    "min_sz": str(i.get("minTradeNum") or "1"), "ct_val": 1.0,
                    "live": str(i.get("symbolStatus")) == "normal", "inst": s,
                    "maker": float(i.get("makerFeeRate") or 0), "taker": float(i.get("takerFeeRate") or 0),
                    "min_usdt": float(i.get("minTradeUSDT") or 0)}
    return _META[s]


def _q(value, step, mode=ROUND_FLOOR):
    """Round to the instrument's step with exactly the step's decimals. Float rounding is how a
    protective stop lands one tick early, and a size under the lot step is a rejection."""
    st = D(str(step))
    if st <= 0:
        raise BrokerError(f"bad step {step}")
    s = str((D(str(value)) / st).to_integral_value(rounding=mode) * st)
    return s


def _px(symbol, price, up):
    """Limit price for a triggered leg: at least one whole tick beyond the trigger, in the
    direction of travel — a stop limit priced ON its trigger can trigger and never fill."""
    tick = D(str(_meta(symbol)["tick"]))
    trig = D(str(price))
    step = max(abs(trig * D(str(SLACK))), tick)
    v = (trig + step) if up else (trig - step)
    v = D(_q(v, tick, ROUND_CEILING if up else ROUND_FLOOR))
    if up and v <= trig:
        v = trig + tick
    if not up and v >= trig:
        v = trig - tick
    if v <= 0:
        raise BrokerError(f"{symbol}: no room for a stop below {price} at tick {tick}")
    return str(v)


# ---------- http + auth ----------
def _ts():
    """Bitget signs with epoch MILLISECONDS as a string; a clock skew over ~30 s is rejected."""
    return str(int(time.time() * 1000))


def _sign(method, path, body, ts):
    key = os.environ.get("BITGET_API_KEY")
    sec = os.environ.get("BITGET_API_SECRET")
    pass_ = os.environ.get("BITGET_API_PASSPHRASE")
    if not (key and sec and pass_):
        raise BrokerError("Bitget needs BITGET_API_KEY + BITGET_API_SECRET + BITGET_API_PASSPHRASE")
    msg = f"{ts}{method}{path}{body}"
    sig = base64.b64encode(hmac.new(sec.encode(), msg.encode(), hashlib.sha256).digest()).decode()
    hdr = {"Content-Type": "application/json", "ACCESS-KEY": key, "ACCESS-SIGN": sig,
           "ACCESS-TIMESTAMP": ts, "ACCESS-PASSPHRASE": pass_}
    if os.environ.get("BITGET_PASS_CODE"):
        hdr["papcode"] = os.environ["BITGET_PASS_CODE"]
    return hdr


def _req(method, path, params=None, body=None, tries=3, public=False):
    """One transport for both shapes Bitget accepts: a query string on GET (signed as the literal
    `k=v&k=v` the URL carries) and JSON on POST. The signature covers path + exactly what is sent,
    so the two must never diverge — that is the whole 60124 error class."""
    qs = ""
    if params:
        qs = "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    signed_path = path + qs
    payload = "" if body is None else json.dumps(body, separators=(",", ":"))
    hdr = {"Accept": "application/json", "User-Agent": UA}
    if not public and not DRY:
        hdr.update(_sign(method, signed_path, payload, _ts()))
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(HOST + signed_path, data=payload.encode() or None,
                                         method=method, headers=hdr)
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            txt = e.read().decode()[:300]
            last = f"HTTP {e.code} {txt}"
            if e.code in (429, 500, 502, 503) and attempt < tries - 1:
                time.sleep(1.2 * (attempt + 1))
                continue
            raise BrokerError(f"{method}{signed_path}: {last}")        # never blind-retry a money call
        except Exception as e:                                          # noqa: BLE001 — network, not logic
            last = f"{type(e).__name__}: {e}"
            time.sleep(1.2 * (attempt + 1))
            continue
        if str(d.get("code")) not in ("00000", "0"):
            raise BrokerError(f"{method}{signed_path}: bitget code {d.get('code')} {d.get('msg')}")
        return d
    raise BrokerError(f"{method}{signed_path}: {last}")


def _rows(d):
    r = (d or {}).get("data")
    return r if isinstance(r, list) else ([r] if r else [])


# ---------- market data (public; the shadow ledger reads the same feed) ----------
def _bars(rows, now_ts=None):
    """Bitget candle row: [ts(ms), OPEN, high, low, CLOSE, volume(coin), quoteVolume] — OLDEST
    FIRST on both /candles and /history-candles, the opposite of OKX, and with no `confirm` flag
    to drop a forming bar. So: drop any bar whose open time has not yet elapsed a full period
    (history-candles returns closed bars only; /candles includes the live one).
    """
    now = now_ts or time.time()
    out = []
    prev = None
    for c in rows or []:
        ts = int(c[0]) / 1000.0
        o, h, l, cl = float(c[1]), float(c[2]), float(c[3]), float(c[4])
        if not (h >= max(o, cl) >= min(o, cl) >= l):
            raise BrokerError(f"candles: impossible bar {c}")
        out.append({"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts)),
                    "o": o, "h": h, "l": l, "c": cl, "v": float(c[5]) if len(c) > 5 else 0.0,
                    "_ts": ts})
        prev = ts
    period = 3600.0
    if len(out) >= 3:
        period = out[-1]["_ts"] - out[-2]["_ts"] or 3600.0
    out = [b for b in out if b["_ts"] + period <= now + 1]      # the forming bar is never scored
    for b in out:
        b.pop("_ts", None)
    out.sort(key=lambda b: b["t"])
    return out


def crypto_bars(symbol, timeframe="1Hour", limit=200):
    """history-candles returns CLOSED bars only — no forming-bar trap — and is the same series the
    live triggers price against, which is what makes paper and live comparable to the tick."""
    gran = BAR.get(timeframe)
    if gran not in GRANULARITY_OK:            # a silent fallback to 1H here would fake a 5m scan
        raise BrokerError(f"{timeframe!r} is not a Bitget history-candles granularity "
                          f"(known: {', '.join(sorted(GRANULARITY_OK))})")
    d = _req("GET", "/api/v2/mix/market/history-candles",
             params={"symbol": _sym(symbol), "productType": PRODUCT, "granularity": gran,
                     "limit": max(3, min(int(limit), 1000))}, public=True)
    return _bars(_rows(d))


def last_price(symbol):
    d = _req("GET", "/api/v2/mix/market/ticker",
             params={"symbol": _sym(symbol), "productType": PRODUCT}, public=True)
    rows = _rows(d)
    if not rows:
        raise BrokerError(f"{_sym(symbol)}: no ticker")
    return float(rows[0]["lastPr"])


# ---------- wallet ----------
def account():
    """Equity is the USDT margin equity (unrealised PnL included) — run_cycle caps NOTIONAL at
    max_notional_frac of it, so the leverage the bot can reach stays under 1x by construction.
    Field names are read defensively: Bitget renames these between classic and unified accounts,
    and a KeyError on a wallet call stops a cycle that should never have been about the wallet."""
    if DRY or not os.environ.get("BITGET_API_KEY"):
        eq = float(os.environ.get("BITGET_DRY_EQUITY") or 100000.0)
        return {"equity": eq, "cash": eq, "crypto_value": 0.0}
    rows = _rows(_req("GET", "/api/v2/mix/account/account",
                      params={"symbol": "BTCUSDT", "productType": PRODUCT, "marginCoin": MARGIN_COIN}))
    if not rows:
        return {"equity": 0.0, "cash": 0.0, "crypto_value": 0.0}
    a = rows[0]
    def f(*names):
        for n in names:
            v = a.get(n)
            if v not in (None, ""):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        return 0.0
    eq = f("usdtEquity", "accountEquity", "equity", "marginSize") or f("fixedBalance")
    cash = f("available", "availableBalance", "crossAvailable", "isolatedAvailable")
    return {"equity": round(eq, 2), "cash": round(cash, 2), "crypto_value": round(max(0.0, eq - cash), 2)}


def positions():
    """Signed qty: positive long, negative short — run_cycle's `side` test reads the sign. In
    one-way mode Bitget returns one row per hold side, `holdSide` saying which."""
    if DRY or not os.environ.get("BITGET_API_KEY"):
        return []
    out = []
    rows = _rows(_req("GET", "/api/v2/mix/position/all-position",
                      params={"productType": PRODUCT, "marginCoin": MARGIN_COIN}))
    for p in rows:
        try:
            pos = float(p.get("total") or p.get("available") or 0)
        except (TypeError, ValueError):
            pos = 0.0
        if pos == 0:
            continue
        sign = -1.0 if str(p.get("holdSide")).lower().startswith("s") else 1.0
        sym = str(p.get("symbol") or "").upper().replace("USDT", "") + "/USD"
        try:
            mark = float(p.get("markPrice") or 0) or None
        except (TypeError, ValueError):
            mark = None
        # SANITY GUARD, not decoration: if size*entry is wildly off the venue's own notional, the
        # units are not coins and this bot is about to manage a book it misreads by 1000x.
        try:
            entry = float(p.get("openPriceAvg") or 0) or None
        except (TypeError, ValueError):
            entry = None
        notional = p.get("totalNotional") or p.get("notionalUsd")
        if notional and entry:
            try:
                n, implied = float(notional), pos * entry
                if n > 0 and not (0.2 <= implied / n <= 5.0):
                    raise BrokerError(f"position units disagree: size*avg={implied:,.2f} vs venue "
                                      f"notional={n:,.2f} — Bitget returned something other than coins")
            except ValueError:
                pass
        out.append({"symbol": sym, "qty": sign * pos, "avg_entry_price": entry,
                    "current_price": mark})
    return out


# ---------- orders ----------
_ST = {"1": "open", "2": "open", "3": "open", "4": "filled", "5": "canceled", "6": "canceled",
       "partially_filled": "open", "live": "open", "filled": "filled", "canceled": "canceled",
       "cancelled": "canceled", "new": "open"}


def _norm(o):
    side = str(o.get("side") or "").lower()
    st = str(o.get("state") or o.get("status") or "").lower()
    def fl(k):
        v = o.get(k)
        try:
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None
    return {"id": o.get("orderId") or o.get("entrustId"),
            "client_order_id": o.get("clientOid") or o.get("clOrdId"),
            "symbol": str(o.get("symbol") or "").upper().replace("USDT", "") + "/USD",
            "side": side, "type": str(o.get("orderType") or o.get("ordType") or "limit").lower(),
            "status": _ST.get(st, st),
            "qty": fl("totalVolume") or fl("size") or 0.0,
            "filled_qty": fl("dealVolume") or 0.0,
            "filled_avg_price": fl("priceAvg") or fl("dealAvgPrice"),
            "limit_price": fl("price") or fl("executePrice"),
            "stop_price": fl("triggerPrice")}


def open_orders(symbol=None):
    if DRY or not os.environ.get("BITGET_API_KEY"):
        return []
    rows = _rows(_req("GET", "/api/v2/mix/order/orders-pending",
                      params={"productType": PRODUCT, "symbol": _sym(symbol) if symbol else None}))
    return [_norm(o) for o in rows]


def order_by_cid(cid):
    """The round trip: our cid -> clientOid -> the venue's own order object. Pending first, then
    history (a fill can happen inside the same 300 s cycle). If this cannot find a freshly placed
    order the bot is trading blind and must stop."""
    if DRY or not os.environ.get("BITGET_API_KEY"):
        return None
    oid = oid_for(cid)
    for sym in (None,):
        for path in ("/api/v2/mix/order/detail", "/api/v2/mix/order/orders-history"):
            params = {"symbol": _sym(sym) if sym else None, "clientOid": oid, "productType": PRODUCT,
                      "limit": "50"}
            if path.endswith("orders-history"):
                params["orderIdList"] = json.dumps([oid])
            try:
                rows = _rows(_req("GET", path, params={k: v for k, v in params.items() if v}))
            except BrokerError:
                rows = []
            for r in rows:
                if str(r.get("clientOid") or "") == oid or path.endswith("detail"):
                    return _norm(r)
    for o in open_orders():
        if o.get("client_order_id") == oid:
            return o
    return None


def fills(symbol=None, order_id=None):
    if DRY or not os.environ.get("BITGET_API_KEY"):
        return []
    rows = _rows(_req("GET", "/api/v2/mix/order/fills",
                      params={"productType": PRODUCT, "symbol": _sym(symbol) if symbol else None,
                              "limit": "50"}))
    out = []
    for f in rows:
        if order_id and str(f.get("orderId")) != str(order_id):
            continue
        try:
            fee = abs(float(f.get("totalFee") or 0))
        except (TypeError, ValueError):
            fee = 0.0
        out.append({"price": float(f.get("price") or 0), "size": float(f.get("volume") or 0),
                    "side": str(f.get("side") or f.get("direction") or "").lower(),
                    "order_id": f.get("orderId"), "fee": fee,
                    "feeCcy": f.get("feeCoin") or MARGIN_COIN, "time": str(f.get("timestamp") or "")})
    return out


def _body(side, inst, sz, px, otype, trigger, tp, sl, cid, symbol):
    """One place a real Bitget order is described. Returns (path, body). Single endpoint for every
    order type — a trigger is a field, not a different URL."""
    b = {"symbol": inst, "productType": PRODUCT.upper(), "marginMode": MARGIN,
         "marginCoin": MARGIN_COIN, "size": sz, "side": side,
         "clientOid": oid_for(cid) if cid else None}
    b = {k: v for k, v in b.items() if v is not None}
    if HEDGE:
        b["tradeSide"] = "close" if otype == "market_close" else "open"
    if tp or sl:                                        # protective legs ride on the entry order
        if tp:
            b["presetStopSurplusPrice"] = str(tp)
        if sl:
            b["presetStopLossPrice"] = str(sl)
    if otype in ("stop", "stop_limit", "buy_stop", "sell_stop", "sell_stop_limit"):
        trig = trigger or px
        b["orderType"] = "limit"
        b["triggerType"] = "fill_price"                  # last price, which is what the scan saw
        b["triggerPrice"] = str(trig)
        b["executePrice"] = _px(symbol, trig, side == "buy") if otype in (
            "stop", "buy_stop", "sell_stop") else str(px or _px(symbol, trig, side == "buy"))
        b["executeDelay"] = False
        if not HEDGE:
            b["reduceOnly"] = "NO"
    elif otype == "market":
        b["orderType"] = "market"
    elif otype == "limit":
        b["orderType"] = "limit"
        b["price"] = str(px)
        b["force"] = "gtc"
    else:
        raise BrokerError(f"unsupported order type: {otype}")
    return "/api/v2/mix/order/place-order", b


def place_order(side, symbol, qty=None, notional=None, otype="limit", limit_price=None,
                stop_price=None, tif="gtc", cid=None, tp=None, sl=None):
    """side buy/sell · qty in COINS (Bitget sizes in coins, no contract multiplier) · tp/sl attach
    to the entry order so protection exists from the first second on the venue's engine."""
    side = "buy" if str(side).lower().startswith("b") else "sell"
    m = _meta(symbol)
    if not m["live"]:
        raise BrokerError(f"{m['inst']} is not tradeable on Bitget right now ({PRODUCT})")
    ref = stop_price or limit_price or last_price(symbol)
    coins = float(qty) if qty is not None else float(notional or 0) / float(ref)
    if coins <= 0:
        raise BrokerError("zero or negative size")
    sz = _q(coins, m["lot"])
    if float(sz) < float(m["min_sz"]) or float(sz) <= 0:
        raise BrokerError(f"{m['inst']}: size {coins:.8g} coins is below minTradeNum {m['min_sz']}")
    px = _q(limit_price, m["tick"]) if limit_price else None
    trig = _q(stop_price, m["tick"]) if stop_price else None
    path, body = _body(side, m["inst"], sz, px, otype, trig,
                       _q(tp, m["tick"]) if tp else None, _q(sl, m["tick"]) if sl else None, cid, symbol)
    notional_now = float(body.get("price") or body.get("executePrice") or ref) * float(sz)
    if notional_now < m["min_usdt"]:
        raise BrokerError(f"{m['inst']}: {sz} @ ~{notional_now:,.2f} USDT is under the venue's "
                          f"minTradeUSDT {m['min_usdt']}")
    if DRY or not os.environ.get("BITGET_API_KEY"):
        print(f"  DRY [{'sim' if SIM else 'live'}] POST {path} {json.dumps(body)}")
        return {"id": f"dry{int(time.time() * 1000)}", "client_order_id": body["clientOid"],
                "symbol": symbol, "side": side, "type": otype, "qty": float(sz), "status": "open",
                "limit_price": float(body.get("price") or body.get("executePrice") or 0) or None,
                "stop_price": float(body.get("triggerPrice") or 0) or None,
                "payload": body, "path": path}
    d = _req("POST", path, body=body)
    r = _rows(d)
    r = r[0] if r else {}
    if str(d.get("code")) not in ("00000", "0"):
        raise BrokerError(f"rejected: code {d.get('code')} {d.get('msg')}")
    return {"id": r.get("orderId"), "client_order_id": r.get("clientOid") or body["clientOid"],
            "symbol": symbol, "side": side, "type": otype, "qty": float(sz), "status": "open",
            "limit_price": float(body.get("price") or body.get("executePrice") or 0) or None,
            "stop_price": float(body.get("triggerPrice") or 0) or None,
            "payload": body, "path": path}


def cancel_order(order_id, symbol=None):
    if DRY or not os.environ.get("BITGET_API_KEY"):
        return {"cancelled": True, "id": order_id, "dry": True}
    body = {"symbol": _sym(symbol) if symbol else "BTCUSDT", "productType": PRODUCT.upper()}
    if symbol:
        body["orderId"] = str(order_id)
    else:
        body["clientOid"] = str(order_id)
        body["orderId"] = str(order_id)                 # one of the two must match; both is legal
    _req("POST", "/api/v2/mix/order/cancel-order", body=body)
    return {"cancelled": True, "id": order_id}


def cancel_for(symbol):
    """PER-SYMBOL cleanup only. A `cancel_all` was once run locally and destroyed two resting
    entries on another book; this adapter never exposes it, and callers must pass a symbol."""
    out = []
    for o in open_orders(symbol):
        oid = o.get("id")
        if oid:
            try:
                cancel_order(oid, symbol=symbol)
                out.append(oid)
            except BrokerError as e:
                out.append(f"{oid}: {e}")
    return out


# ---------- operator tools (read-only unless DRY) ----------
def verify():
    """Print the wallet and the venue's own fee schedule. Nothing is sent, nothing is cancelled."""
    acct = account()
    print(f"  Bitget wallet: equity ${acct['equity']:,.2f} · cash ${acct['cash']:,.2f} · "
          f"{len(positions())} positions · mode {'hedge' if HEDGE else 'one-way'} · margin {MARGIN}")
    for s in ("BTC/USD", "ETH/USD", "SOL/USD"):
        m = _meta(s)
        print(f"  {m['inst']:9s} tick {m['tick']} size-step {m['lot']} minTradeNum {m['min_sz']} "
              f"min {m['min_usdt']} USDT · maker {100 * m['maker']:.2f} % taker {100 * m['taker']:.2f} %")
    return acct


def fees():
    """The number that decides whether this venue is worth trading at all, read live."""
    tot = []
    for s in ("BTC/USD", "ETH/USD", "XRP/USD", "SOL/USD", "DOGE/USD", "ADA/USD", "LINK/USD",
              "LTC/USD", "BCH/USD", "AVAX/USD"):
        m = _meta(s)
        px = last_price(s)
        # Two numbers, because they answer different questions and mixing them up is how a venue
        # gets judged as cheap on an assumption the live guard does not make:
        #   best  = entry leg fills as maker, exit at the stop as taker  (what the tape usually does)
        #   guard = taker BOTH legs, which is what broker_ledger.round_trip_fees and therefore
        #           `live_max_fee_r` actually compute — and the entry leg is a trigger on Bitget
        #           (executePrice crossing into the market), so the guard number is the honest one.
        best = (m["maker"] + m["taker"]) / 0.005
        guard = 2 * m["taker"] / 0.005
        tot.append((best, guard))
        print(f"  {m['inst']:9s} {px:>11,.4g}  mkr {100 * m['maker']:.2f}% tkr {100 * m['taker']:.2f}%"
              f"  -> 0.50 % stop pays {best:.2f}R (maker entry) / {guard:.2f}R (taker both)"
              f"   {'OK vs live_max_fee_r' if guard <= 0.25 else 'OVER CAP — signals get refused'}")
    mb = sum(a for a, _ in tot) / len(tot)
    mg = sum(b for _, b in tot) / len(tot)
    print(f"  mean {mb:.3f}R optimistic · {mg:.3f}R as the live guard measures it "
          f"(cap 0.250R) · headroom {0.25 - mg:+.3f}R")
    print("  the guard number is the one that decides: this book's entries are triggers, so the venue "
          "charges taker on both legs nearly always.")
    return mg


def rehearse():
    """DRY only: build every order shape the bot uses, against LIVE prices and real increments."""
    if not (DRY or SIM):
        raise SystemExit("rehearse needs BITGET_DRY=1 or BITGET_SIM=1 — it would place real orders")
    for sym, otype in (("BTC/USD", "limit"), ("ETH/USD", "stop"), ("SOL/USD", "limit"),
                       ("XRP/USD", "stop"), ("DOGE/USD", "limit"), ("AVAX/USD", "stop")):
        px = last_price(sym)
        m = _meta(sym)
        side = "buy" if otype == "limit" else "sell"
        r = float(px) * 0.005
        out = place_order(side, sym, qty=round(100.0 / r, 8), otype=otype,
                          limit_price=px if otype == "limit" else None,
                          stop_price=None if otype == "limit" else px,
                          tp=px + 3 * r, sl=px - r if side == "buy" else px + r,
                          cid=f"sentry{sym.replace('/', '')}{int(time.time() * 1000)}n1")
        b = out["payload"]
        print(f"  {sym:9s} {otype:6s} -> size {b['size']} side {b['side']} "
              f"{'trig ' + b.get('triggerPrice', '-') + ' exec ' + b.get('executePrice', '-') if 'triggerPrice' in b else 'px ' + b.get('price', '-')} "
              f"tp {b.get('presetStopSurplusPrice', '-')} sl {b.get('presetStopLossPrice', '-')} "
              f"| on tick {m['tick']}, size step {m['lot']}")
    print("  payloads built for 6 symbols; nothing was sent (DRY)." if DRY else "  SIM engine: see host")


if __name__ == "__main__":
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "verify").lower()
    {"verify": verify, "fees": fees, "rehearse": rehearse}.get(
        cmd, verify)()
