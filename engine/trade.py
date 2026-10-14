#!/usr/bin/env python3
"""Discretionary trade CLI (Muse's book). Used in scheduled sessions.

  python3 trade.py buy  --cond 0x... --token <tid> --usd 5 --reason "..."
  python3 trade.py close --token <tid> --reason "..."
  python3 trade.py status
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pm_api import gamma_markets  # noqa: E402
from ledger import load_state, buy, sell, equity, MAX_TRADE_USD  # noqa: E402
import dashboard  # noqa: E402

ROOT = os.path.expanduser("~/workspace/poly-llm")
CAND = os.path.join(ROOT, "state", "candidates.json")


def resolve(cond, token):
    ms = gamma_markets({"condition_id": cond, "limit": 1})
    if not ms:
        return None, "market not found"
    m = ms[0]
    try:
        tids = json.loads(m.get("clobTokenIds") or "[]")
    except (ValueError, TypeError):
        return None, "no token ids"
    side = "Yes" if str(tids[0]) == str(token) else "No"
    return {"market": m, "side": side,
            "question": m.get("question", "")}, None


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("buy")
    b.add_argument("--cond", required=True)
    b.add_argument("--token", required=True)
    b.add_argument("--usd", type=float, required=True)
    b.add_argument("--reason", required=True)
    c = sub.add_parser("close")
    c.add_argument("--token", required=True)
    c.add_argument("--reason", default="manual close")
    sub.add_parser("status")
    a = ap.parse_args()

    s = load_state()
    if a.cmd == "status":
        e = equity(s)
        print(json.dumps({**{k: round(v, 2) for k, v in e.items()},
                          "open": len(s["positions"]),
                          "halted": s.get("halted")}, indent=1))
        return
    if a.cmd == "buy":
        if a.usd > MAX_TRADE_USD:
            print(json.dumps({"ok": False, "error": "exceeds $5 cap"}))
            return
        info, err = resolve(a.cond, a.token)
        if err:
            print(json.dumps({"ok": False, "error": err}))
            return
        pos, err = buy(s, book="disc", token_id=a.token,
                       condition_id=a.cond, question=info["question"],
                       side=info["side"], usd=a.usd, market=info["market"],
                       reason=a.reason)
        print(json.dumps({"ok": err is None, "error": err,
                          "price": round(pos["avg_price"], 4) if pos else None}))
    elif a.cmd == "close":
        r, err = sell(s, a.token, reason=a.reason)
        print(json.dumps({"ok": err is None, "error": err,
                          "realized": round(r or 0, 2)}))
    dashboard.render()


if __name__ == "__main__":
    main()
