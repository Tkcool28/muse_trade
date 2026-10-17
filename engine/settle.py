#!/usr/bin/env python3
"""Settlement pass: check open positions for resolution, book P&L, sweep."""
import json

from pm_api import gamma_market_by_condition, gamma_market_by_id
from ledger import (load_state, save_state, settle_position, sweep_check,
                    check_halt, log_event)


def market_for(p):
    """Resolve a position's market for settlement.

    Prefers the stored Gamma market id: the /markets?condition_ids= listing
    hides resolved markets (verified 2026-10-17 — Oct-15 positions sat open
    2 days showing mark 1.00), while /markets/{id} returns them with full
    umaResolutionStatus/outcomePrices. Falls back to condition lookup.
    """
    mid = (p or {}).get("market_id")
    if mid:
        try:
            m = gamma_market_by_id(mid)
            if m:
                return m
        except RuntimeError:
            pass
    try:
        return gamma_market_by_condition(p["condition_id"])
    except RuntimeError:
        return None


def is_resolved(market):
    if not market or not market.get("closed"):
        return None
    if market.get("umaResolutionStatus") != "resolved":
        return None
    try:
        ops = json.loads(market.get("outcomePrices") or "[]")
    except (ValueError, TypeError):
        return None
    if len(ops) < 1:
        return None
    # index 0 = Yes token, 1 = No token (matches clobTokenIds order)
    if ops[0] in ("1", "1.0", 1, 1.0):
        return "Yes"
    if len(ops) > 1 and ops[1] in ("1", "1.0", 1, 1.0):
        return "No"
    return None


def run_settle(s):
    events = []
    for tid in list(s["positions"]):
        p = s["positions"][tid]
        m = market_for(p)
        winner = is_resolved(m)
        if winner is None:
            continue
        win = (p["side"] == winner)
        r, err = settle_position(s, tid, win)
        if err:
            events.append({"event": "settle_error", "token": tid, "error": err})
        else:
            events.append({"event": "settled", "question": p["question"][:60],
                           "side": p["side"], "win": win,
                           "realized": round(r, 2)})
    swept = sweep_check(s)
    for a in swept:
        events.append({"event": "sweep", "amount": a})
    if check_halt(s):
        events.append({"event": "halt", "reason": s["halt_reason"]})
    return events


if __name__ == "__main__":
    s = load_state()
    evs = run_settle(s)
    save_state(s)
    print(json.dumps(evs, indent=1))
