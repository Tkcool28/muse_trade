#!/usr/bin/env python3
"""Copy-trading half: mirror evaluated wallets' BUYs (direction only, our size).

Detection latency is real: we fill at the executable price observed when the
hook first sees the wallet's trade. Never backfilled.
"""
import json
import os
import time

from pm_api import data_activity, gamma_markets, clob_price, book_depth_ok
from ledger import (load_state, save_state, buy, sell, tied_up, log_event,
                    MAX_TRADE_USD)

ROOT = os.path.expanduser("~/workspace/poly-llm")
WALLETS = os.path.join(ROOT, "state", "wallets.json")

COPY_USD = 5.0
COPY_BOOK_TIED_CAP = 60.0
MAX_ADVERSE_MOVE = 0.04
MAX_HOLD_DAYS = 45
STALE_HOURS = 6


def load_wallets():
    if not os.path.exists(WALLETS):
        return {"wallets": []}
    with open(WALLETS) as f:
        return json.load(f)


def save_wallets(w):
    tmp = WALLETS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(w, f, indent=1)
    os.replace(tmp, WALLETS)


def market_for(condition_id):
    try:
        ms = gamma_markets({"condition_id": condition_id, "limit": 1})
    except RuntimeError:
        return None
    return ms[0] if ms else None


def token_side(market, token_id):
    try:
        tids = json.loads(market.get("clobTokenIds") or "[]")
    except (ValueError, TypeError):
        return None
    if not tids:
        return None
    return "Yes" if str(tids[0]) == str(token_id) else "No"


def days_to_end(market):
    try:
        end = time.mktime(time.strptime(market.get("endDate") or "",
                                        "%Y-%m-%dT%H:%M:%SZ"))
        return (end - time.time()) / 86400.0
    except (ValueError, TypeError):
        return None


def copy_book_tied(s):
    return sum(p["cost"] for p in s["positions"].values()
               if p.get("book") == "copy")


def try_copy_buy(s, w, act):
    """Evaluate one wallet BUY against the copy filters. Returns event|None."""
    tid = str(act.get("token_id") or act.get("asset"))
    cond = act.get("condition_id") or act.get("conditionId")
    if not tid or not cond:
        return None
    if tid in s["positions"]:
        return None  # already hold it; no doubling
    m = market_for(cond)
    if not m or m.get("closed"):
        return None
    dte = days_to_end(m)
    if dte is None or dte > MAX_HOLD_DAYS or dte < 0:
        return None
    side = token_side(m, tid)
    if not side:
        return None
    wprice = float(act.get("price") or 0)
    try:
        our_price = clob_price(tid, "BUY")
    except RuntimeError:
        return None
    if not (0 < our_price < 1):
        return None
    if wprice > 0 and (our_price - wprice) / wprice > MAX_ADVERSE_MOVE:
        return {"event": "copy_skip",
                "reason": f"price moved {(our_price-wprice)/wprice:.1%} adverse",
                "question": m.get("question", "")[:60]}
    shares = COPY_USD / our_price
    if not book_depth_ok(tid, "BUY", shares, 3.0):
        return {"event": "copy_skip", "reason": "thin book",
                "question": m.get("question", "")[:60]}
    if copy_book_tied(s) + COPY_USD > COPY_BOOK_TIED_CAP:
        return {"event": "copy_skip", "reason": "copy book tied-up cap",
                "question": m.get("question", "")[:60]}
    pos, err = buy(s, book="copy", token_id=tid, condition_id=cond,
                   question=m.get("question", ""), side=side, usd=COPY_USD,
                   market=m, wallet=w["address"],
                   reason=f"copy {w.get('name', w['address'][:8])} @ {wprice:.3f}")
    if err:
        return {"event": "copy_skip", "reason": err,
                "question": m.get("question", "")[:60]}
    w["copied_trades"] = w.get("copied_trades", 0) + 1
    return {"event": "copy_buy", "question": m.get("question", "")[:60],
            "side": side, "price": round(our_price, 3),
            "wallet": w.get("name", w["address"][:8])}


def run_copy(s):
    events = []
    wstate = load_wallets()
    for w in wstate["wallets"]:
        if w.get("status") != "active":
            continue
        addr = w["address"]
        try:
            acts = data_activity(addr, limit=100)
        except RuntimeError as e:
            events.append({"event": "wallet_error", "wallet": addr[:10],
                           "error": str(e)[:80]})
            continue
        wm = w.get("watermark", 0)
        fresh = [a for a in acts if (a.get("timestamp") or 0) > wm]
        fresh.sort(key=lambda a: a.get("timestamp") or 0)
        for a in fresh:
            ts = a.get("timestamp") or 0
            w["watermark"] = max(w.get("watermark", 0), ts)
            if ts < time.time() - STALE_HOURS * 3600:
                continue  # first sight but stale; don't chase
            atype = a.get("type")
            tid = str(a.get("token_id") or a.get("asset") or "")
            if atype == "TRADE" and a.get("side") == "BUY":
                ev = try_copy_buy(s, w, a)
                if ev:
                    events.append(ev)
            elif atype == "TRADE" and a.get("side") == "SELL":
                p = s["positions"].get(tid)
                if p and p.get("book") == "copy":
                    r, err = sell(s, tid,
                                 reason=f"wallet {w.get('name','?')} exited")
                    events.append({"event": "copy_exit",
                                   "question": p["question"][:60],
                                   "realized": round(r or 0, 2),
                                   "error": err})
            # REDEEM: our settle pass handles resolution
        save_wallets(wstate)
    recompute_wallet_stats(s, wstate)
    save_wallets(wstate)
    return events


def recompute_wallet_stats(s, wstate=None):
    """Derive per-wallet copied trades/P&L from the ledger (audit trail)."""
    wstate = wstate or load_wallets()
    stats = {}
    try:
        with open(os.path.join(ROOT, "state", "ledger.jsonl")) as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                wa = e.get("wallet")
                if not wa:
                    continue
                st = stats.setdefault(wa, {"trades": 0, "pnl": 0.0})
                if e.get("type") == "fill":
                    st["trades"] += 1
                elif e.get("type") in ("close", "settle"):
                    st["pnl"] += float(e.get("realized") or 0)
    except FileNotFoundError:
        pass
    for w in wstate["wallets"]:
        st = stats.get(w["address"], {"trades": 0, "pnl": 0.0})
        w["copied_trades"] = st["trades"]
        w["copied_pnl"] = round(st["pnl"], 2)
        if (w.get("status") == "active" and st["trades"] >= 10
                and st["pnl"] < 0):
            w["status"] = "dropped"
            log_event("wallet_dropped", wallet=w["address"],
                      reason=f"{st['trades']} copied trades, P&L ${st['pnl']:.2f}")
    return wstate


if __name__ == "__main__":
    s = load_state()
    evs = run_copy(s)
    save_state(s)
    print(json.dumps(evs, indent=1))
