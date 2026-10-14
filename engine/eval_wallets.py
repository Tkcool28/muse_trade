#!/usr/bin/env python3
"""Evaluate copy-wallet candidates from the public leaderboard + activity.

Gates (Terry's): active enough that a $200 bank doesn't get tied up in
months-long trades. Filters: >=8 trades/30d, median hold <=21d, last trade
<=5d ago, real closes (REDEEMs), directional (not market-maker churn).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pm_api import data_leaderboard, data_activity  # noqa: E402

NOW = time.time()
D30 = 30 * 86400


def stats_for(addr):
    try:
        acts = data_activity(addr, limit=400)
    except RuntimeError as e:
        return {"error": str(e)[:60]}
    recent = [a for a in acts if (a.get("timestamp") or 0) > NOW - D30]
    buys = [a for a in recent if a.get("type") == "TRADE"
            and a.get("side") == "BUY"]
    sells = [a for a in recent if a.get("type") == "TRADE"
             and a.get("side") == "SELL"]
    redeems = [a for a in recent if a.get("type") == "REDEEM"]
    # hold times: first BUY -> last SELL/REDEEM per token
    first_buy, last_exit = {}, {}
    for a in recent:
        tid = str(a.get("token_id") or a.get("asset") or "")
        ts = a.get("timestamp") or 0
        if not tid:
            continue
        if a.get("type") == "TRADE" and a.get("side") == "BUY":
            first_buy[tid] = min(first_buy.get(tid, ts), ts)
        elif (a.get("type") == "REDEEM"
              or (a.get("type") == "TRADE" and a.get("side") == "SELL")):
            last_exit[tid] = max(last_exit.get(tid, ts), ts)
    holds = [(last_exit[t] - first_buy[t]) / 86400.0
             for t in first_buy if t in last_exit]
    holds.sort()
    med_hold = holds[len(holds) // 2] if holds else None
    last_ts = max([a.get("timestamp") or 0 for a in recent] or [0])
    n_tr = len([a for a in recent if a.get("type") == "TRADE"])
    mm_ratio = (len(sells) / max(1, len(buys)))  # ~1 = two-sided churn
    return {
        "trades_30d": n_tr, "buys": len(buys), "sells": len(sells),
        "redeems": len(redeems), "closed_pairs": len(holds),
        "median_hold_d": round(med_hold, 1) if med_hold is not None else None,
        "last_trade_days_ago": round((NOW - last_ts) / 86400.0, 1)
        if last_ts else None,
        "mm_ratio": round(mm_ratio, 2),
    }


def main():
    top = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    lb = data_leaderboard(limit=top)
    rows = []
    for i, w in enumerate(lb):
        addr = w.get("user_id") or w.get("proxy_wallet") or ""
        name = w.get("user_name") or addr[:10]
        st = stats_for(addr)
        st.update({"rank": w.get("rank", i + 1), "name": name,
                   "address": addr, "pnl": round(w.get("pnl") or 0, 0),
                   "volume": round(w.get("volume") or 0, 0)})
        rows.append(st)
        print(f"[{i+1}/{len(lb)}] {name}: {st['trades_30d']} trades/30d, "
              f"hold {st['median_hold_d']}d, last {st['last_trade_days_ago']}d ago",
              flush=True)
        time.sleep(0.3)
    out = os.path.expanduser("~/workspace/poly-llm/state/wallet_eval.json")
    with open(out, "w") as f:
        json.dump({"ts": int(NOW), "rows": rows}, f, indent=1)
    print("wrote", out)


if __name__ == "__main__":
    main()
