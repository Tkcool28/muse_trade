#!/usr/bin/env python3
"""Paper ledger: cash, positions, sweeps, P&L. All fills simulated, fees real."""
import json
import os
import time

from pm_api import clob_price, clob_midpoint
from fees import taker_fee, GAS_PER_FILL

ROOT = os.path.expanduser("~/workspace/poly-llm")
STATE = os.path.join(ROOT, "state", "state.json")
LEDGER = os.path.join(ROOT, "state", "ledger.jsonl")

START_BANK = 200.0
BOOK_START = 100.0
MAX_TRADE_USD = 5.0
MAX_TIED_UP = 120.0
HALT_EQUITY = 160.0
DAILY_LOSS_BRAKE = 15.0
SWEEP_STEP = 25.0


def now():
    return int(time.time())


def fresh_state():
    return {
        "cash": START_BANK,
        "sweep": 0.0,
        "swept_total": 0.0,
        "realized_pnl": 0.0,
        "fees_paid": 0.0,
        "books": {"copy": {"realized": 0.0}, "disc": {"realized": 0.0}},
        "positions": {},
        "halted": False,
        "halt_reason": None,
        "daily": {"date": time.strftime("%Y-%m-%d"), "realized": 0.0},
        "started_ts": now(),
    }


def load_state():
    if not os.path.exists(STATE):
        s = fresh_state()
        save_state(s)
        return s
    with open(STATE) as f:
        return json.load(f)


def save_state(s):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(s, f, indent=1)
    os.replace(tmp, STATE)


def log_event(etype, **kw):
    kw.update({"ts": now(), "type": etype})
    with open(LEDGER, "a") as f:
        f.write(json.dumps(kw) + "\n")


def _roll_day(s):
    today = time.strftime("%Y-%m-%d")
    if s["daily"]["date"] != today:
        s["daily"] = {"date": today, "realized": 0.0}


def tied_up(s):
    return sum(p["cost"] for p in s["positions"].values())


def refresh_marks(s):
    for tid, p in s["positions"].items():
        try:
            p["last_price"] = clob_midpoint(tid)
        except RuntimeError:
            pass


def unrealized(s):
    tot = 0.0
    for p in s["positions"].values():
        lp = p.get("last_price") or p["avg_price"]
        tot += (lp - p["avg_price"]) * p["shares"]
    return tot


def equity(s):
    refresh_marks(s)
    t = tied_up(s)
    un = unrealized(s)
    return {
        "cash": s["cash"], "tied_up": t, "unrealized": un,
        "bank_equity": s["cash"] + t + un,
        "sweep": s["sweep"], "realized_pnl": s["realized_pnl"],
        "fees_paid": s["fees_paid"],
    }


def _guard(s, book, usd_extra=0.0):
    _roll_day(s)
    if s["halted"]:
        return "halted: " + str(s["halt_reason"])
    if usd_extra > MAX_TRADE_USD + 1e-9:
        return f"trade ${usd_extra:.2f} exceeds ${MAX_TRADE_USD:.2f} cap"
    if tied_up(s) + usd_extra > MAX_TIED_UP + 1e-9:
        return "bank tied-up cap $120 reached"
    if s["daily"]["realized"] <= -DAILY_LOSS_BRAKE:
        return "daily loss brake hit"
    if s["cash"] < usd_extra:
        return "insufficient cash"
    return None


def buy(s, *, book, token_id, condition_id, question, side, usd, market,
        reason=None, wallet=None):
    """Paper taker BUY of `usd` notional. Returns (position, None) or (None, err)."""
    tid = str(token_id)
    err = _guard(s, book, usd)
    if err:
        return None, err
    try:
        price = clob_price(tid, "BUY")
    except RuntimeError as e:
        return None, f"price fetch failed: {e}"
    if not (0 < price < 1):
        return None, f"bad price {price}"
    shares = usd / price
    fee = taker_fee(shares, price, market) + GAS_PER_FILL
    total = usd + fee
    if s["cash"] < total:
        return None, "insufficient cash for cost+fee"
    s["cash"] -= total
    s["fees_paid"] += fee
    p = s["positions"].get(tid)
    if p:
        tot_sh = p["shares"] + shares
        p["avg_price"] = (p["avg_price"] * p["shares"] + price * shares) / tot_sh
        p["shares"] = tot_sh
        p["cost"] += total
    else:
        s["positions"][tid] = {
            "condition_id": condition_id, "question": question, "side": side,
            "shares": shares, "avg_price": price, "cost": total,
            "last_price": price, "book": book, "opened_ts": now(),
            "reason": reason, "wallet": wallet,
            "end_date": (market or {}).get("endDate"),
        }
    log_event("fill", book=book, token_id=tid, question=question, side=side,
              usd=round(usd, 2), price=round(price, 4),
              shares=round(shares, 2), fee=round(fee, 4),
              reason=reason, wallet=wallet)
    save_state(s)
    return s["positions"][tid], None


def _close(s, tid, proceeds_net, how, reason=None):
    p = s["positions"].pop(tid)
    realized = proceeds_net - p["cost"]
    s["cash"] += proceeds_net
    s["realized_pnl"] += realized
    s["books"][p["book"]]["realized"] += realized
    _roll_day(s)
    s["daily"]["realized"] += realized
    log_event(how, book=p["book"], token_id=tid, question=p["question"],
              side=p["side"], shares=round(p["shares"], 2),
              proceeds=round(proceeds_net, 2),
              realized=round(realized, 2), reason=reason or p.get("reason"),
              wallet=p.get("wallet"))
    save_state(s)
    return realized


def sell(s, token_id, reason=None):
    """Paper taker SELL of full position at the bid."""
    tid = str(token_id)
    err = _guard(s, None)
    if err:
        return None, err
    p = s["positions"].get(tid)
    if not p:
        return None, "no position"
    try:
        price = clob_price(tid, "SELL")
    except RuntimeError as e:
        return None, f"price fetch failed: {e}"
    fee = taker_fee(p["shares"], price, None) + GAS_PER_FILL
    s["fees_paid"] += fee
    proceeds = p["shares"] * price - fee
    r = _close(s, tid, proceeds, "close", reason)
    return r, None


def settle_position(s, token_id, win):
    """Resolution settle: winners $1.00/share, losers $0. No redemption fee."""
    tid = str(token_id)
    p = s["positions"].get(tid)
    if not p:
        return None, "no position"
    proceeds = p["shares"] * 1.0 if win else 0.0
    r = _close(s, tid, proceeds, "settle",
               reason=f"resolved {'WIN' if win else 'LOSS'}")
    return r, None


def sweep_check(s):
    """Move $25 chunks of unswept realized profit to the sweep account."""
    swept = []
    while s["realized_pnl"] - s["swept_total"] >= SWEEP_STEP - 1e-9:
        amt = min(SWEEP_STEP, s["cash"])
        if amt < SWEEP_STEP - 1e-9:
            break  # can't sweep what isn't liquid; wait for settles
        s["cash"] -= amt
        s["sweep"] += amt
        s["swept_total"] += amt
        log_event("sweep", amount=round(amt, 2), sweep_total=round(s["sweep"], 2))
        swept.append(amt)
    if swept:
        save_state(s)
    return swept


def check_halt(s):
    e = equity(s)
    if not s["halted"] and e["bank_equity"] < HALT_EQUITY:
        s["halted"] = True
        s["halt_reason"] = f"equity ${e['bank_equity']:.2f} < $160 drawdown halt"
        log_event("halt", reason=s["halt_reason"])
        save_state(s)
        return True
    return False


def book_pnl(s, book):
    return s["books"][book]["realized"]
