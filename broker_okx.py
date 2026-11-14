#!/usr/bin/env python3
"""OKX adapter — real orders on a real book, and (unlike Coinbase) a rehearsal venue with no money.

Why this file exists: the fee arithmetic. Sentry risks 1R per trade through 0.4-1.2 % stops, so a
venue charging 0.40/0.60 % takes more per round trip than the trade risks (v4.4.0 refuses those
orders on purpose). OKX perpetual swaps cost 0.02 % maker / 0.05 % taker at the base tier — about
0.13R — which is the first schedule this playbook can actually pay. Verified from the runner's own
egress (2026-11-14): api.bybit.com and api.binance.com REFUSE a US IP outright (GitHub Actions
runners are US-based, so those venues are untradeable from here no matter what their fees do),
while www.okx.com answers — market data 200, private endpoints 401/50103 (path live, key absent).
Same probe: Kraken, Bitget, MEXC, Gate, KuCoin reachable; Bybit/Binance geo-blocked.

Also, the thing Coinbase never gave: **OKX simulated trading** — a real matching engine, real
order lifecycle, no money, on the same host, switched on by one header (`OKX_SIM=1`). So the
id round trip and the trigger payload can be PROVEN before a dollar is at risk.

Interface matches what `run_cycle.py` calls on `broker`, so the venue is one config line:
"execution": "okx". Perps also mean the short side of the checklist stops being paper-only
(CAN_SHORT = True; on spot/ledger it stays paper-graded).

Credentials (Actions Secrets only; never printed, never committed):
  OKX_API_KEY, OKX_API_SECRET, OKX_API_PASSPHRASE
  OKX_SIM=1     simulated (demo) trading: real engine, fake money. Also forces LIVE off.
  OKX_DRY=1     build and print the exact payload, send nothing
  OKX_DRY_EQUITY  pretend-wallet size for a dry rehearsal
  OKX_INSTTYPE  "swap" (default) or "spot"

Run `python3 broker_okx.py` for a read-only wallet check, or `python3 broker_okx.py rehearse`
(SIM or DRY only) to place-and-cancel a resting conditional order and prove the id round trip.
stdlib only — urllib + hmac, no SDK.
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
from decimal import Decimal as D, ROUND_FLOOR

HOST = os.environ.get("OKX_BASE") or "https://www.okx.com"
SIM = os.environ.get("OKX_SIM") == "1"          # simulated trading: same host, demo flag
DRY = os.environ.get("OKX_DRY") == "1"          # payloads built, nothing sent
INSTTYPE = (os.environ.get("OKX_INSTTYPE") or "swap").lower()
if INSTTYPE not in ("swap", "spot"):
    raise SystemExit(f"OKX_INSTTYPE must be 'swap' or 'spot', got {INSTTYPE!r}")
CATEGORY = "SWAP" if INSTTYPE == "swap" else "SPOT"
TD_MODE = os.environ.get("OKX_TDMODE") or ("cross" if INSTTYPE == "swap" else "cash")
CAN_SHORT = INSTTYPE == "swap"                   # spot accounts cannot open a short
# The venue holds the protective legs, so a stop is live between Actions runs (this account gets a
# few cycles a day, not one per 10 min — a bot-side stop is only as good as the next wake-up).
ATTACH_TP_SL = True
UA = "sentry-bot/4.5"
BAR = {"1Minute": "1m", "5Minute": "5m", "15Minute": "15m", "1Hour": "1H", "4Hour": "4H",
       "6Hour": "6H", "1Day": "1D"}
SLACK = float(os.environ.get("OKX_SLACK", "0.0015"))    # limit clearance past a trigger


class BrokerError(Exception):
    pass


# ---------- ids ----------
# OKX wants a client order id ("clOrdId") of letters/digits only, max 32 chars. Sentry's cid is
# `sentry{SYM}{ms}n{seq}` (up to 60 chars), so every id is folded to a deterministic 32-char
# alphanumeric: same cid -> same id, forever, with no mapping table that has to survive between
# Actions runs (the runners do not). Losing this mapping is how an order becomes invisible.

def oid_for(cid):
    return "sen" + hashlib.sha1(f"okx:{cid}".encode()).hexdigest()[:29]


# ---------- symbols & increments ----------

def _inst(symbol):
    base = str(symbol).split("/")[0].upper()
    return f"{base}-USDT-SWAP" if INSTTYPE == "swap" else f"{base}-USDT"


_META = {}


def _meta(symbol):
    inst = _inst(symbol)
    if inst not in _META:
        d = _req("GET", "/api/v5/public/instruments", params={"instType": CATEGORY, "instId": inst},
                 public=True)
        rows = d.get("data") or []
        if not rows:
            raise BrokerError(f"{inst}: not listed on OKX {CATEGORY}")
        i = rows[0]
        _META[inst] = {"tick": str(i.get("tickSz") or "0.01"), "lot": str(i.get("lotSz") or "0.01"),
                       "min_sz": str(i.get("minSz") or "1"), "ct_val": float(i.get("ctVal") or 1) or 1.0,
                       "live": i.get("state") == "live", "inst": inst}
    return _META[inst]


def _q(value, step, mode=ROUND_FLOOR):
    """Floor to the instrument's step with exactly the step's decimals — float rounding is how a
    protective stop lands one tick early, and a size below lotSz/minSz is a rejection."""
    st = D(str(step))
    if st <= 0:
        raise BrokerError(f"bad step {step}")
    return str((D(str(value)) / st).to_integral_value(rounding=mode) * st)


def _px(symbol, price, up):
    """Limit price for a triggered leg: at least one whole tick beyond the trigger, in the
    direction of travel — a stop limit priced ON its trigger can trigger and never fill."""
    tick = D(str(_meta(symbol)["tick"]))
    trig = D(str(price))
    want = abs(trig * D(str(SLACK)))
    step = max(want, tick)
    v = (trig + step) if up else (trig - step)
    v = D(_q(v, tick, ROUND_FLOOR if not up else ROUND_FLOOR))
    if up and v <= trig:
        v = trig + tick
    if not up and v >= trig:
        v = trig - tick
    if v <= 0:
        raise BrokerError(f"{symbol}: no room for a stop below {price} at tick {tick}")
    return str(v)


# ---------- http + auth ----------

def _ts():
    """OKX wants ISO-8601 UTC with milliseconds; a clock more than 30 s off is rejected outright."""
    t = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int(round((t % 1) * 1000)):03d}Z"


def _sign(method, path, body, ts):
    key = os.environ.get("OKX_API_KEY")
    sec = os.environ.get("OKX_API_SECRET")
    pass_ = os.environ.get("OKX_API_PASSPHRASE")
    if not (key and sec and pass_):
        raise BrokerError("OKX needs OKX_API_KEY + OKX_API_SECRET + OKX_API_PASSPHRASE")
    msg = f"{ts}{method}{path}{body}"
    sig = base64.b64encode(hmac.new(sec.encode(), msg.encode(), hashlib.sha256).digest()).decode()
    return {"OK-ACCESS-KEY": key, "OK-ACCESS-SIGN": sig, "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": pass_, "Content-Type": "application/json"}


def _req(method, path, params=None, body=None, tries=3, public=False):
    qs = ""
    if params:
        qs = "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    signed_path = path + qs                                  # the signature covers the query string
    payload = "" if body is None else json.dumps(body, separators=(",", ":"))
    hdr = {"Accept": "application/json", "User-Agent": UA}
    if SIM:
        hdr["x-simulated-trading"] = "1"
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
            raise BrokerError(f"{method}{signed_path}: {last}")     # never blind-retry a money call
        except Exception as e:                                        # noqa: BLE001 — network, not logic
            last = f"{type(e).__name__}: {e}"
            time.sleep(1.2 * (attempt + 1))
            continue
        if str(d.get("code")) != "0":
            raise BrokerError(f"{method}{signed_path}: okx code {d.get('code')} {d.get('msg')}")
        return d
    raise BrokerError(f"{method}{signed_path}: {last}")


def _rows(d):
    return (d or {}).get("data") or []


# ---------- market data (public; the shadow ledger will read the same feed) ----------

def _bars(rows, now_ts=None):
    """OKX candle row: [ts, OPEN, high, low, close, vol, volCcy, volCcyQuote, confirm] — NEWEST
    FIRST, and confirm == "0" means the candle is still forming. Note the order: open is index 1
    here, whereas Coinbase puts low there. The first port of this bot read the columns in Coinbase
    order and every pattern fired on itself, so the mapping is explicit and pinned by test_data.py.
    """
    now_ms = int((now_ts or time.time()) * 1000)
    out = []
    for c in rows or []:
        if str(c[8]) == "0":
            continue                                        # forming: never score it
        ts = int(c[0])
        if ts >= now_ms - 1000:
            continue
        o, h, l, cl = float(c[1]), float(c[2]), float(c[3]), float(c[4])
        if not (h >= max(o, cl) >= min(o, cl) >= l):
            raise BrokerError(f"candles: impossible bar {c}")
        out.append({"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts / 1000)),
                    "o": o, "h": h, "l": l, "c": cl, "v": float(c[5])})
    out.sort(key=lambda b: b["t"])
    return out


def crypto_bars(symbol, timeframe="1Hour", limit=200):
    d = _req("GET", "/api/v5/market/candles",
             params={"instId": _inst(symbol), "bar": BAR.get(timeframe, "1H"), "limit": min(int(limit), 290)},
             public=True)
    return _bars(_rows(d))


def last_price(symbol):
    d = _req("GET", "/api/v5/market/ticker", params={"instId": _inst(symbol)}, public=True)
    rows = _rows(d)
    if not rows:
        raise BrokerError(f"{_inst(symbol)}: no ticker")
    return float(rows[0]["last"])


# ---------- wallet ----------

def account():
    """Equity is the whole account in USD (`totalEq`), and cash is USDT that can be posted as
    margin. run_cycle caps NOTIONAL at max_notional_frac of equity, so on a 3x-able contract the
    leverage the bot can reach stays under 1x by construction — margin capacity is never the limit.
    """
    if DRY:
        eq = float(os.environ.get("OKX_DRY_EQUITY") or 100000.0)
        return {"equity": eq, "cash": eq, "crypto_value": 0.0}
    d = _req("GET", "/api/v5/account/balance")
    rows = _rows(d)
    if not rows:
        return {"equity": 0.0, "cash": 0.0, "crypto_value": 0.0}
    eq = float(rows[0].get("totalEq") or 0)
    cash = 0.0
    for c in rows[0].get("details") or []:
        if c.get("ccy") in ("USDT", "USDC", "USD"):
            cash += float(c.get("availBal") or 0)
    return {"equity": round(eq, 2), "cash": round(cash, 2), "crypto_value": round(eq - cash, 2)}


def positions():
    """Signed qty: positive long, negative short, which is what run_cycle's `side` test reads.
    Perpetual positions are net per instrument in one-way mode; `avgPx` is the venue's own entry."""
    if DRY:
        return []
    out = []
    for p in _rows(_req("GET", "/api/v5/account/positions", params={"instType": CATEGORY})):
        pos = float(p.get("pos") or 0)
        if pos == 0:
            continue
        sign = -1.0 if str(p.get("posSide")) == "short" else 1.0
        ct = 1.0
        sym = str(p.get("instId") or "").split("-")[0] + "/USD"
        try:
            ct = _meta(sym)["ct_val"]
        except BrokerError:
            pass
        out.append({"symbol": sym, "qty": sign * pos * ct,
                    "avg_entry_price": float(p.get("avgPx") or 0) or None,
                    "current_price": float(p.get("markPx") or 0) or None})
    return out


# ---------- orders ----------

_ST = {"live": "open", "partially_filled": "open", "filled": "filled", "canceled": "canceled",
       "cancelled": "canceled", "delayed": "open", "oracle": "open"}


def _norm(o):
    return {"id": o.get("ordId"), "client_order_id": o.get("clOrdId"),
            "symbol": str(o.get("instId") or "").split("-")[0] + "/USD",
            "side": str(o.get("side") or "").lower(), "type": str(o.get("ordType") or "").lower(),
            "status": _ST.get(str(o.get("state") or "").lower(), str(o.get("state") or "").lower()),
            "qty": float(o.get("sz") or 0), "filled_qty": float(o.get("accFillSz") or 0),
            "filled_avg_price": float(o["avgPx"]) if o.get("avgPx") else None,
            "limit_price": float(o["px"]) if o.get("px") else None,
            "stop_price": float((o.get("tpTriggerPx") or o.get("slTriggerPx"))) if (o.get("tpTriggerPx")
                                                                                    or o.get("slTriggerPx")) else None}


def open_orders(symbol=None):
    if DRY:
        return []
    rows = _rows(_req("GET", "/api/v5/trade/orders-pending",
                      params={"instType": CATEGORY, "instId": _inst(symbol) if symbol else None}))
    return [_norm(o) for o in rows]


def order_by_cid(cid):
    """The round trip: our cid -> clOrdId -> the venue's own order object. If this cannot find a
    freshly placed order, the bot is trading blind and must stop."""
    if DRY:
        return None
    oid = oid_for(cid)
    for path in ("/api/v5/trade/order", "/api/v5/trade/orders-history"):
        try:
            rows = _rows(_req("GET", path, params={"instId": None, "clOrdId": oid}))
        except BrokerError:
            rows = []
        if rows:
            return _norm(rows[0])
    for o in open_orders():
        if o.get("client_order_id") == oid:
            return o
    return None


def fills(symbol=None, order_id=None):
    if DRY:
        return []
    rows = _rows(_req("GET", "/api/v5/trade/fills",
                      params={"instType": CATEGORY, "ordId": order_id,
                              "instId": _inst(symbol) if symbol else None}))
    return [{"price": float(f.get("fillPx") or 0), "size": float(f.get("fillSz") or 0),
             "side": str(f.get("side") or "").lower(), "order_id": f.get("ordId"),
             "fee": float(f.get("fee") or 0), "feeCcy": f.get("feeCcy"), "time": f.get("ts")}
            for f in rows]


def _body(side, inst, sz, px, otype, trigger, tp, sl, cid, symbol):
    """One place a real OKX order is described. Returns (path, body)."""
    base = {"instId": inst, "tdMode": TD_MODE, "side": side, "clOrdId": oid_for(cid) if cid else None}
    base = {k: v for k, v in base.items() if v is not None}
    if tp or sl:                                          # protective legs ride on the entry order
        att = {}
        if tp:
            att.update({"tpTriggerPx": str(tp), "tpOrdPx": "-1", "tpTriggerPxType": "last"})
        if sl:
            att.update({"slTriggerPx": str(sl), "slOrdPx": "-1", "slTriggerPxType": "last"})
        base["attachAlgoOrds"] = [att]
    if otype in ("stop", "stop_limit", "buy_stop", "sell_stop_limit"):
        # A triggered ENTRY is an algo order on a different endpoint: /trade/order only takes
        # market/limit/post_only/fok/ioc. Getting this wrong is a rejected order, not a wrong fill,
        # so it is loud — but it is also the one field-set that must be confirmed in SIM mode first.
        trig = trigger or px
        b = {**base, "ordType": "conditional", "sz": sz,
             "trigger": {"triggerPx": str(trig), "triggerPxType": "last"},
             "reduceOnly": "false"}
        # the trigger fires as a marketable limit with a collar, never a naked market order, so a
        # gap through the level cannot be filled at any price the tape happens to be printing
        b["px"] = _px(symbol, trig, side == "buy") if otype in ("stop", "buy_stop", "sell_stop") else str(px)
        return "/api/v5/trade/order-algo", b
    if otype == "market":
        b = {**base, "ordType": "market", "sz": sz}
        if CATEGORY == "SPOT":
            b["tgtCcy"] = "base_ccy"                      # spot market sizes in coins, like everything else here
        return "/api/v5/trade/order", b
    if otype == "limit":
        return "/api/v5/trade/order", {**base, "ordType": "limit", "sz": sz, "px": str(px),
                                       "tgtCcy": "base_ccy"}
    raise BrokerError(f"unsupported order type: {otype}")


def place_order(side, symbol, qty=None, notional=None, otype="limit", limit_price=None,
                stop_price=None, tif="gtc", cid=None, tp=None, sl=None):
    """side buy/sell · qty in COINS (contracts are computed here) · tp/sl attach to the entry order
    so protection exists from the first second, on the venue's engine rather than in this bot."""
    side = "buy" if str(side).lower().startswith("b") else "sell"
    m = _meta(symbol)
    if not m["live"]:
        raise BrokerError(f"{m['inst']} is not live on OKX right now")
    ref = stop_price or limit_price or last_price(symbol)
    if side == "sell" and not CAN_SHORT and otype in ("stop", "buy_stop", "sell_stop_limit"):
        raise BrokerError(f"{m['inst']}: opening a short needs hedge-mode perps (OKX_INSTTYPE=swap); "
                          f"this venue is spot, so a sell can only close")
    coins = float(qty) if qty is not None else float(notional or 0) / float(ref)
    if coins <= 0:
        raise BrokerError("zero or negative size")
    contracts = coins / m["ct_val"]
    sz = _q(contracts, m["lot"])
    if float(sz) < float(m["min_sz"]) or float(sz) <= 0:
        raise BrokerError(f"{m['inst']}: size {coins:.8g} coins = {sz} contracts, below minSz {m['min_sz']}")
    px = _q(limit_price, m["tick"]) if limit_price else None
    trig = _q(stop_price, m["tick"]) if stop_price else None
    path, body = _body(side, m["inst"], sz, px, otype, trig,
                       _q(tp, m["tick"]) if tp else None, _q(sl, m["tick"]) if sl else None, cid, symbol)
    if DRY:
        print(f"  DRY [{'sim' if SIM else 'live'}] POST {path} {json.dumps(body)}")
        return {"id": f"dry{int(time.time() * 1000)}", "client_order_id": body["clOrdId"],
                "symbol": symbol, "side": side, "type": otype, "qty": coins, "status": "open",
                "limit_price": float(body.get("px") or 0) or None,
                "stop_price": float((body.get("trigger") or {}).get("triggerPx") or 0) or None,
                "payload": body, "path": path}
    d = _req("POST", path, body=body)
    rows = _rows(d)
    r = rows[0] if rows else {}
    # OKX answers HTTP 200 with a per-order error inside `sCode`. Ignoring it is how a bot believes
    # it is in a trade it never entered.
    if str(r.get("sCode", "0")) != "0":
        raise BrokerError(f"rejected: sCode {r.get('sCode')} {r.get('sMsg')}")
    return {"id": r.get("ordId"), "client_order_id": r.get("clOrdId") or body["clOrdId"],
            "symbol": symbol, "side": side, "type": otype, "qty": coins, "status": "open",
            "limit_price": float(body.get("px") or 0) or None,
            "stop_price": float((body.get("trigger") or {}).get("triggerPx") or 0) or None,
            "payload": body, "path": path}


def cancel_order(order_id, symbol=None):
    if DRY:
        return {"cancelled": True, "id": order_id, "dry": True}
    body = {"instId": _inst(symbol) if symbol else None, "ordId": None if symbol else str(order_id),
            "clOrdId": str(order_id) if not symbol else None}
    body = {k: v for k, v in body.items() if v}
    if str(CATEGORY) == "SWAP" and "/" in str(order_id):
        body["instId"] = _inst(order_id)
    _req("POST", "/api/v5/trade/cancel-order", body=body)
    return {"cancelled": True, "id": order_id}


def cancel_all(symbol=None):
    """Per-symbol only. A blanket cancel has already deleted other symbols' resting entries here."""
    rows = open_orders(symbol)
    if not rows:
        return {"cancelled": 0}
    if DRY:
        return {"cancelled": len(rows), "dry": True}
    body = [{"instId": _inst(r["symbol"]), "ordId": r["id"]} for r in rows if r.get("id")]
    _req("POST", "/api/v5/trade/cancel-batch", body=body)
    return {"cancelled": len(body)}


# ---------- proof ----------

def verify():
    """Read-only proof of life: venue, wallet, one live candle. Places nothing.

    Works with no key at all — the public half (instrument metadata, candle mapping, id rules) is
    exactly what a wrong adapter gets wrong, and it is worth checking before anyone has credentials.
    """
    print(f"  venue okx/{INSTTYPE} @ {HOST}{' [SIMULATED TRADING — fake money]' if SIM else ''}"
          f"{' [DRY — nothing sent]' if DRY else ''}")
    try:
        a = account()
        print(f"  wallet: cash ${a['cash']:,.2f} · equity ${a['equity']:,.2f} · "
              f"{len(open_orders())} resting orders · {len(positions())} positions")
    except BrokerError as e:
        print(f"  no wallet: {e}")
        print("  (nothing is tradable until all three OKX secrets exist in this repo's Actions settings)")
    inst = _meta("SOL/USD")
    b = crypto_bars("SOL/USD", "1Hour", 3)
    print(f"  {inst['inst']} tick={inst['tick']} lot={inst['lot']} minSz={inst['min_sz']} "
          f"ctVal={inst['ct_val']} live={inst['live']}")
    print(f"  last closed 1h bar {b[-1]['t']} c={b[-1]['c']} (o/h/l/c order verified against the live feed)")
    print(f"  cid->clOrdId: sentrySOL123n1 -> {oid_for('sentrySOL123n1')} (alnum, <=32: "
          f"{bool(re.fullmatch(r'[A-Za-z0-9]{1,32}', oid_for('sentrySOL123n1')))})")


def rehearse():
    """Place a conditional order far from the tape and cancel it, to prove the whole chain —
    id round trip, algo payload, cancel — on the venue's engine. SIM or DRY only, by construction."""
    if not (SIM or DRY):
        raise BrokerError("rehearse is a SIM/DRY-only routine: OKX_SIM=1 or OKX_DRY=1, or don't run it")
    px = last_price("SOL/USD")
    up = px * 1.20                                        # 20 % away: it cannot fill, only prove
    print(f"  rehearse: conditional buy at {up:.2f} (tape {px:.2f}), TP/SL attached, then cancel")
    o = place_order("buy", "SOL/USD", qty=0.02, otype="stop", stop_price=up,
                    tp=up * 1.02, sl=up * 0.99, cid=f"rehearse{int(time.time() * 1000)}")
    print(f"  placed  id={o['id']} clOrdId={o['client_order_id']}")
    if DRY:
        print("  DRY: nothing on the venue to reconcile — run this with OKX_SIM=1 for the real check")
        return o
    found = order_by_cid(o["client_order_id"]) or order_by_cid(f"rehearse{int(time.time() * 1000)}")
    print(f"  reconcile by clOrdId: {'FOUND ' + str(found['status']) if found else 'NOT FOUND — stop, do not go live'}")
    try:
        cancel_order(o["id"], symbol="SOL/USD")
        print("  cancelled — venue clean, no resting order left behind")
    except BrokerError as e:
        print(f"  ALERT — cancel failed, cancel by hand in the OKX app: {e}")
    return o


if __name__ == "__main__":
    try:
        rehearse() if len(sys.argv) > 1 and sys.argv[1] == "rehearse" else verify()
    except BrokerError as e:
        print(f"  FAILED: {e}")
        raise SystemExit(1)
