//+------------------------------------------------------------------+
//| Sentry.mq5  —  an Expert Advisor you can read                    |
//|                                                                  |
//| Why this file exists: the "MT5 bot" service that was asked about |
//| ships no source, no checksum and no vendor — a stranger hands    |
//| over an unsigned .ex5 over Telegram after you pay, and that file |
//| then holds order rights inside the terminal that already holds   |
//| your broker session. This is the same capability with the parts  |
//| that matter written down: sizing from your OWN record, a risk    |
//| clamp tied to equity, a hold switch that lives in the order      |
//| path (not in the UI), and refusals that name the guard that      |
//| bound. The guard arithmetic mirrors tools/mac/fx_guards.py, which |
//| is unit-tested (17 cases) on the Python side.                   |
//|                                                                  |
//| STATUS: never compiled. There is no MetaEditor in the sandbox    |
//| that wrote this. Compile it in MetaEditor on your machine, watch |
//| it on a DEMO terminal first, and treat it as unproven until a    |
//| backtest or a demo week says otherwise. It will not place orders |
//| on a live account unless InpAckRealMoney is set true by you.     |
//+------------------------------------------------------------------+
#property copyright "Sentry — readable EA, no vendor, no download"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//--- inputs: the numbers that decide whether a trade happens at all
input double InpRiskPctOfEquity   = 1.0;      // risk per trade, % of equity (NOT a fixed dollar band)
input double InpMaxRiskUSD        = 25.0;     // absolute ceiling per trade, 0 = do not apply one
input double InpStopFloorPts      = 250;      // minimum stop distance in points (spread noise is not a risk level)
input double InpMaxSpreadPts      = 60;       // refuse new entries when the spread is wider than this
input double InpMaxLots           = 0.0;      // 0 = no ceiling beyond the risk maths
input int    InpDailyOrderCap     = 4;        // pending entries this EA may open per day
input bool   InpAckRealMoney      = false;    // must be true before a LIVE (non-demo) account gets an order
input int    InpEmaFast           = 20;
input int    InpEmaSlow           = 50;
input int    InpRsiPeriod         = 14;
input int    InpMagic             = 20261115; // only this EA's orders are ever touched
input string InpComment           = "Sentry";

CTrade   trade;
int      hEmaFast = INVALID_HANDLE, hEmaSlow = INVALID_HANDLE, hRsi = INVALID_HANDLE;

//--- the manual hold sits in the order path: a file on disk outranks every UI switch
bool Held()
  {
   return (::FileExists("Sentry_hold.flag") != false);
  }

//--- one line per decision, so the journal and the terminal agree about what happened
void Log(string what)
  {
   Print("SENTRY ", TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS), " ", what);
   int fh = ::FileOpen("Sentry_journal.csv", FILE_WRITE | FILE_CSV | FILE_COMMON, ',');
   if(fh != INVALID_HANDLE)
     {
      FileWrite(fh, TimeToString(TimeCurrent(), TIME_DATE | TIME_SECONDS), _Symbol, what);
      FileClose(fh);
     }
  }

bool IsDemo()
  {
   ENUM_ACCOUNT_TRADE_MODE m = (ENUM_ACCOUNT_TRADE_MODE)AccountInfoInteger(ACCOUNT_TRADE_MODE);
   return (m == ACCOUNT_TRADE_DEMO || m == ACCOUNT_TRADE_TEST);
  }

//--- how many pending entries this EA already has open today, straight from its own deal history
int OrdersToday()
  {
   int n = 0;
   datetime day0 = iTime(_Symbol, PERIOD_D1, 0);
   for(int i = OrdersHistoryTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_HISTORY)) continue;
      if(OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
      if(OrderGetInteger(ORDER_TYPE) != ORDER_TYPE_BUY_STOP &&
         OrderGetInteger(ORDER_TYPE) != ORDER_TYPE_SELL_STOP) continue;
      if(OrderGetInteger(ORDER_TIME_SETUP) >= day0) n++;
     }
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
      n++;
     }
   return n;
  }

//--- risk -> lots. Returns 0.0 and a reason when the trade must not happen.
double SizeFor(double stopPts, string &why)
  {
   double equity = AccountInfoDouble(ACCOUNT_EQUITY);
   if(equity <= 0.0)
     {
      why = "HOLD — equity reads 0; a wallet we cannot see is not a wallet with no limit";
      return 0.0;
     }
   if(!IsDemo() && !InpAckRealMoney)
     {
      why = "GATE — real account but InpAckRealMoney is false; no new entries";
      return 0.0;
     }
   double tickVal  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double tickSize = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double point    = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(tickVal <= 0.0 || tickSize <= 0.0 || point <= 0.0)
     {
      why = "HOLD — symbol specs unreadable";
      return 0.0;
     }
   double lossPerLot = stopPts * point / tickSize * tickVal;          // $ lost if the stop is hit, 1.0 lot
   if(lossPerLot <= 0.0)
     {
      why = "HOLD — stop distance produces no measurable loss";
      return 0.0;
     }
   double budget = equity * InpRiskPctOfEquity / 100.0;
   if(InpMaxRiskUSD > 0.0) budget = MathMin(budget, InpMaxRiskUSD);
   double vmin  = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vstep = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double v     = budget / lossPerLot;
   if(vstep > 0.0) v = MathFloor(v / vstep + 1e-9) * vstep;
   v = NormalizeDouble(v, 8);
   if(v < vmin)
     {
      double minRisk = vmin * lossPerLot;
      why = StringFormat("REFUSED — the smallest lot this broker allows (%g) risks $%.2f, %.1f%% of a $%.2f "
                         "account and %.1fx the %.1f%% budget. Not a strategy problem: at this size the "
                         "instrument cannot be traded. Fund to ~$%.0f or use a cent account.",
                         vmin, minRisk, 100.0 * minRisk / equity, equity,
                         minRisk / MathMax(budget, 1e-9), InpRiskPctOfEquity, budget / (InpRiskPctOfEquity / 100.0));
      return 0.0;
     }
   if(InpMaxLots > 0.0 && v > InpMaxLots)
     {
      v = MathFloor(InpMaxLots / vstep + 1e-9) * vstep;
      why = StringFormat("CAPPED — lot ceiling %g applied", InpMaxLots);
      Log(why);
     }
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   if(v > vmax) v = vmax;
   why = StringFormat("sized %.2f lots, risk $%.2f of $%.2f budget", v, v * lossPerLot, budget);
   return v;
  }

bool OnePerSymbol()
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      if(!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
      if(OrderGetString(ORDER_SYMBOL) == _Symbol && OrderGetInteger(ORDER_MAGIC) == InpMagic) return false;
     }
   return true;
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(20);
   hEmaFast = iMA(_Symbol, _Period, InpEmaFast, 0, MODE_EMA, PRICE_CLOSE);
   hEmaSlow = iMA(_Symbol, _Period, InpEmaSlow, 0, MODE_EMA, PRICE_CLOSE);
   hRsi     = iRSI(_Symbol, _Period, InpRsiPeriod, PRICE_CLOSE);
   if(hEmaFast == INVALID_HANDLE || hEmaSlow == INVALID_HANDLE || hRsi == INVALID_HANDLE)
     {
      Log("HOLD — indicator handles failed to build");
      return(INIT_FAILED);
     }
   Log(StringFormat("start · %s %s · equity $%.2f · risk %.1f%% (cap $%.2f) · %s",
                    _Symbol, EnumToString(_Period), AccountInfoDouble(ACCOUNT_EQUITY),
                    InpRiskPctOfEquity, InpMaxRiskUSD, IsDemo() ? "DEMO account" : "REAL account, acked"));
   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason) { Log("stop, reason " + IntegerToString(reason)); }

//+------------------------------------------------------------------+
void OnTick()
  {
   if(Held()) return;                                        // paused: measuring continues, nothing opens
   double bid = SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double ask = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(bid <= 0.0 || ask <= 0.0 || point <= 0.0) return;

   double spreadPts = (ask - bid) / point;
   if(!OnePerSymbol()) return;
   if(OrdersToday() >= InpDailyOrderCap) return;
   if(spreadPts > InpMaxSpreadPts)
     {
      Log(StringFormat("SKIP — spread %.0f pts over the %.0f limit", spreadPts, InpMaxSpreadPts));
      return;
     }

   double f[3], s[3], r[3];
   if(CopyBuffer(hEmaFast, 0, 1, 3, f) < 3 || CopyBuffer(hEmaSlow, 0, 1, 3, s) < 3 ||
      CopyBuffer(hRsi, 0, 1, 3, r) < 3)
      return;
   int dir = 0;                                              // +1 long, -1 short, 0 nothing
   if(f[2] > s[2] && r[2] < 55.0 && r[1] > r[2]) dir = 1;   // trend up, pullback releasing
   else if(f[2] < s[2] && r[2] > 45.0 && r[1] < r[2]) dir = -1;
   if(dir == 0) return;

   double atrPts = MathMax(MathAbs(f[1] - s[1]) / point, InpStopFloorPts);
   string why = "";
   double vol = SizeFor(atrPts, why);
   if(vol <= 0.0)
     {
      Log(why);
      return;
     }
   if(dir > 0)
     {
      double p = NormalizeDouble(ask, _Digits);
      double sl = NormalizeDouble(p - atrPts * point, _Digits);
      double tp = NormalizeDouble(p + 2.0 * atrPts * point, _Digits);
      if(trade.BuyStop(vol, p, _Symbol, sl, tp, ORDER_TIME_GTC, 0, InpComment))
         Log(StringFormat("ORDER SENT — buy stop %.2f @ %.*f sl %.*f tp %.*f (%s)",
                          vol, _Digits, p, _Digits, sl, _Digits, tp, why));
      else
         Log("SEND FAILED retcode " + IntegerToString(trade.ResultRetcode()));
     }
   else
     {
      double p = NormalizeDouble(bid, _Digits);
      double sl = NormalizeDouble(p + atrPts * point, _Digits);
      double tp = NormalizeDouble(p - 2.0 * atrPts * point, _Digits);
      if(trade.SellStop(vol, p, _Symbol, sl, tp, ORDER_TIME_GTC, 0, InpComment))
         Log(StringFormat("ORDER SENT — sell stop %.2f @ %.*f sl %.*f tp %.*f (%s)",
                          vol, _Digits, p, _Digits, sl, _Digits, tp, why));
      else
         Log("SEND FAILED retcode " + IntegerToString(trade.ResultRetcode()));
     }
  }
//+------------------------------------------------------------------+
