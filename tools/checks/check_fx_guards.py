"""check_fx_guards — prove the FX build's guards refuse for the RIGHT reason, on numbers we can read.

Run:  python3 tools/checks/check_fx_guards.py        (no network, no terminal, 0.1 s)

The prices/lots below are inputs, not claims about a broker: XAUUSD 3,863.45 and the 100-oz standard lot
are what the market ticker and a typical Exness-style spec read like, and the point is the RATIO they
produce against an account size. Every case asserts the refusal text, because a refusal that names the
wrong guard teaches the wrong lesson (that is exactly how the crypto books' 25 % notional cap sat broken
for weeks: it looked like caution while it was arithmetic nobody could satisfy).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mac"))
import fx_guards as g                                                # noqa: E402

FAIL = []
N = [0]


def case(name, cond, detail=""):
    N[0] += 1
    print("  %s  %s%s" % ("PASS" if cond else "FAIL", name, ("  (" + detail + ")") if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


XAU_PX, XAU_LOT, STOP = 3863.45, 100.0, 0.005      # $3,863 of notional per 0.01 lot; 0.5 % stop

# 1. the clamp: equity-relative, tighter-of-two, and it says which one bound
r, w = g.risk_clamp(100000.0, 200.0)
case("a $100k demo account's $200 risk is NOT clamped (guards must not invent limits)", r == 200.0, w)
r, w = g.risk_clamp(500.0, 200.0)
case("a $500 real account wanting $200 is clamped to 1 % = $5", abs(r - 5.0) < 1e-9, "%.2f %s" % (r, w))
case("...and the note names the equity and the fraction it used", "1.00% of equity $500.00" in w, w)
r, w = g.risk_clamp(500000.0, 900.0, hard_cap=25.0)
case("an absolute cap the CALLER states still binds, and the note says so",
     r == 25.0 and "abs cap $25.00" in w, "%.2f %s" % (r, w))
r, w = g.risk_clamp(500000.0, 900.0)
case("...and with no cap stated, only equity governs ($500k x 1 % = $5,000, so $900 is legal)",
     r == 900.0, "%.2f %s" % (r, w))
r, w = g.risk_clamp(None, 200.0)
case("unreadable equity -> risk 0 and a HOLD message, never 'no limit'",
     r == 0.0 and "hold" in w, "%.2f %s" % (r, w))
r, w = g.risk_clamp(0.0, 200.0)
case("equity 0.0 is treated as unreadable, not as a zero-sized budget that divides", r == 0.0, w)

# 2. the instrument-size wall: the reason $10 cannot trade gold on a standard account
risk, ok, why = g.min_lot_risk(10.0, 0.01, XAU_LOT, STOP, XAU_PX)
case("min lot on gold costs ~$19 of risk ($3,863 notional x 0.5 %)", abs(risk - 19.32) < 0.05, "%.2f" % risk)
case("a $10 account is REFUSED, and the text says the instrument is too big, not the signal",
     ok is False and "smallest order this broker allows" in why and "Not a strategy problem" in why, why)
case("...and it quotes the equity that WOULD make it legal, so the fix is checkable",
     "$1,932" in why or "1932" in why or "1,931" in why, why[-90:])
risk2, ok2, why2 = g.min_lot_risk(10.0, 0.01, 1.0, STOP, XAU_PX)
case("a cent-sized contract (1 oz/lot) is 100x smaller: $0.19 risk, still 1.9 % of $10 -> needs ~$19",
     abs(risk2 - 0.19317) < 0.001 and ok2 is False and "1.9%" in why2 and "Fund to ~$19" in why2,
     "%.5f %s" % (risk2, why2))
risk3, ok3, why3 = g.min_lot_risk(2000.0, 0.01, XAU_LOT, STOP, XAU_PX)
case("...and a funded account clears the identical check", ok3 is True, why3)

# 3. arming: ack, funding, and the manual hold, in the order that matters
case("demo needs no ack (nothing real can move)", g.arming(True, 100000.0, False, True)[0] is True)
case("REAL without live_ack is held", g.arming(False, 500.0, False, True)[0] is False
     and "live_ack" in g.arming(False, 500.0, False, True)[1])
case("REAL + ack + unreadable wallet is held, with the fund-or-disarm wording",
     g.arming(False, None, True, True)[0] is False and "fund the account or disarm" in
     g.arming(False, None, True, True)[1].lower())
case("REAL + ack + funded is allowed", g.arming(False, 10.0, True, True)[0] is True)
case("the desk switch outranks everything, demo included",
     g.arming(True, 100000.0, True, False)[0] is False and "switch is off" in g.arming(True, 100000.0, True, False)[1])

print("\n%s" % ("RESULT: PASS — %d cases" % N[0] if not FAIL else
               "RESULT: FAIL — %d of %d failed: %s" % (len(FAIL), N[0], "; ".join(FAIL))))
sys.exit(1 if FAIL else 0)
