"""fx_guards — the small set of arithmetic gates the FX build must not be without.

Why this file exists. The crypto books (run_cycle.py) grew guards over a month of being wrong in public:
risk tied to a fraction of equity, a wallet check before any order, an explicit ack before real money,
and a refusal that says WHICH guard bound. The FX build (`sentry_mac.py`, which drives MetaQuotes' own MCP
order API inside the terminal) has none of that: its per-trade risk is a hard-coded dollar band
(`RISK = 100.0`, MIN/MAX 50–200) with no relation to the account it is trading. On a $100k demo that reads
as 0.05–0.2 % and is harmless; on a small real account the same $200 is tens of percent of equity, and a
guard that never refuses is not a guard.

Kept deliberately pure: no imports from the build, no I/O, no MCP. Every function takes numbers and
returns (value, reason), so it can be tested here — and so a patch to the deployed build can be a three-line
call, not a rewrite of the order path.
"""

# --- sizing: one place turns "how much do I dare lose" into a number -------------------------------


def risk_clamp(equity, want, max_frac=0.01, hard_cap=None):
    """Return (risk_dollars, note). `want` is whatever the self-sizer picked; the equity-relative limit
    applies always, an absolute dollar cap only when the caller states one. equity None/<=0 means 'the
    wallet was never read' — the caller must treat that as a HOLD, not as 'no limit'.

    hard_cap is a parameter, NOT a default borrowed from the crypto books: their $25 ceiling protects a
    spot/perp book whose per-trade baseline is small, while the FX build's own band is $50–200 by design
    (`RISK`/MIN_RISK/MAX_RISK in sentry_mac.py). Inheriting a number from a sibling book would have
    silently halved every FX trade — which is how cross-porting guards goes wrong.
    """
    if equity is None or float(equity) <= 0.0:
        return 0.0, "no equity read — hold (a wallet we cannot see is not a wallet with no limit)"
    equity = float(equity)
    frac_lim = equity * float(max_frac)
    lim = frac_lim if hard_cap is None else min(frac_lim, float(hard_cap))
    want = float(want)
    if want <= lim:
        return want, "within %.2f%% of equity" % (lim / equity * 100.0)
    return lim, "LIVE RISK CLAMP — $%.2f -> $%.2f (%.2f%% of equity $%.2f%s)" % (
        want, lim, max_frac * 100.0, equity,
        "" if hard_cap is None else ", abs cap $%.2f" % float(hard_cap))


def min_lot_risk(equity, volume_min, contract_size, stop_frac, price, max_frac=0.01):
    """What the SMALLEST order the broker allows costs, and whether that is inside his risk budget.

    A standard lot is not a unit of size, it is a unit of the instrument: on XAUUSD one lot is 100 oz, so
    volume_min 0.01 at $3,863 is $3,863 of notional and a 0.5 % stop is ~$19 of risk. On a $10 account that
    is 190 % of equity: the venue's minimum order is bigger than the account's whole risk budget, and no
    cleverness fixes it. Return (risk_at_min_lot, ok, why).
    """
    # stop_frac is a FRACTION of price (0.005 = half a percent), so risk is notional x that fraction.
    # Getting this wrong by one factor of price is the classic unit bug in this corner of trading code.
    notional = float(volume_min) * float(contract_size) * float(price)
    risk = notional * float(stop_frac)
    if equity is None or float(equity) <= 0.0:
        return risk, False, "no equity read — hold"
    budget = float(equity) * float(max_frac)
    if risk <= budget:
        return risk, True, "min lot risks $%.2f of a $%.2f budget (%.2f%% of equity)" % (
            risk, budget, risk / float(equity) * 100.0)
    return risk, False, (
        "REFUSED — the smallest order this broker allows (volume_min %g) risks $%.2f, which is %.1f%% of a "
        "$%.2f account and %.1fx the %.1f%% per-trade budget. Not a strategy problem: at this size the "
        "instrument cannot be traded at all. Fund to ~$%.0f or trade a cent account."
        % (float(volume_min), risk, risk / float(equity) * 100.0, float(equity),
           risk / budget if budget else 0.0, max_frac * 100.0,
           risk / max_frac if max_frac else 0.0))


# --- arming: what has to be true before a real account may be sent an order ------------------------


def arming(is_demo, equity, ack, switch_on):
    """(allow_new_entries, why). Mirrors the crypto books' live_gate, in the order that matters:
    money needs an ack; a live account needs money; and a manual hold outranks both.
    """
    if not switch_on:
        return False, "held — the desk switch is off"
    if is_demo:
        return True, "demo account — no ack needed, nothing real can move"
    if not ack:
        return False, "REAL account but live_ack is not set — no new entries until you flip it on purpose"
    if equity is None:
        return False, "REAL account, but the wallet could not be read — fund the account or disarm the key"
    if float(equity) <= 0.0:
        return False, "REAL account reads $%.2f equity — nothing to trade" % float(equity)
    return True, "REAL account, acked, funded $%.2f" % float(equity)
