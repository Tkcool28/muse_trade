#!/usr/bin/env python3
"""Shadow signal log — every wallet BUY signal, graded at settlement.

Purpose (Terry, 2026-10-20): a future learner can only learn when NOT to
copy if it sees the outcomes of signals we SKIPPED, not just the trades we
took. So the copy loop records every fresh wallet BUY it evaluates —
copied or skipped, with the decision, the skip reason, and the features at
detection time (our executable price, the wallet's price, fee rate) — and
this module later settles each evaluable signal against the market's real
resolution:

  would_be_pnl  = what a $5 taker copy at the detection-time price would
                  have made held to settlement (real fee model, no fee on
                  redemption — same economics as ledger.settle_position).
  decision_correct:
      copied  -> would_be_pnl > 0   (taking it was right)
      skipped -> would_be_pnl <= 0  (skipping avoided a non-profit)
  reward (learner-facing): copied -> +would_be_pnl; skipped -> -would_be_pnl.

Rows are append-only JSONL in state/signals.jsonl: {"type": "signal", ...}
written by copy.py at detection, {"type": "outcome", ...} appended here at
resolution. Signals whose price was never honestly observable (stale first
sight, no book, unmapped side, closed market) are logged with
evaluable=False and never graded — no invented prices.
"""
import json
import os
import time

from fees import GAS_PER_FILL

ROOT = os.path.expanduser("~/workspace/poly-llm")
SIGNALS = os.path.join(ROOT, "state", "signals.jsonl")

_seen_ids = None  # lazy set of recorded signal_ids (dedupe on crash-retry)


def signal_id(wallet, act_ts, token_id):
    return f"{wallet[:10]}-{act_ts}-{str(token_id)[:12]}"


def _load_seen():
    global _seen_ids
    if _seen_ids is None:
        _seen_ids = set()
        for row in _rows():
            if row.get("type") == "signal":
                _seen_ids.add(row.get("signal_id"))
    return _seen_ids


def _rows():
    if not os.path.exists(SIGNALS):
        return
    with open(SIGNALS) as f:
        for line in f:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def _append(row):
    with open(SIGNALS, "a") as f:
        f.write(json.dumps(row) + "\n")


def record_signal(sig):
    """Append one signal row. Returns True if written (False on duplicate)."""
    seen = _load_seen()
    sid = sig.get("signal_id")
    if sid in seen:
        return False
    row = {"type": "signal", "recorded_ts": int(time.time())}
    row.update(sig)
    _append(row)
    seen.add(sid)
    return True


def would_be_pnl(price, win, fee_rate, usd=5.0):
    """Net P&L of a hypothetical taker copy held to settlement."""
    if not price or not (0 < price < 1):
        return None
    shares = usd / price
    fee = shares * (fee_rate or 0.0) * price * (1.0 - price) + GAS_PER_FILL
    proceeds = shares if win else 0.0
    return proceeds - usd - fee


def load_all():
    signals, outcomes = {}, {}
    for row in _rows():
        if row.get("type") == "signal":
            signals[row["signal_id"]] = row
        elif row.get("type") == "outcome":
            outcomes[row["signal_id"]] = row
    return signals, outcomes


def pending_signals():
    signals, outcomes = load_all()
    return [s for sid, s in signals.items()
            if s.get("evaluable") and sid not in outcomes]


def settle_signals(max_checks=30):
    """Grade up to max_checks pending signals (oldest first) whose markets
    have resolved. Returns outcome events for the run summary."""
    from settle import market_for, is_resolved  # deferred: avoids any cycle

    events = []
    pend = sorted(pending_signals(), key=lambda s: s.get("act_ts", 0))
    for s in pend[:max_checks]:
        m = market_for({"market_id": s.get("market_id"),
                        "condition_id": s.get("condition_id")})
        winner = is_resolved(m)
        if winner is None:
            continue
        win = (s.get("side") == winner)
        pnl = would_be_pnl(s.get("our_price"), win, s.get("fee_rate"),
                           usd=s.get("usd", 5.0))
        if pnl is None:
            continue
        copied = s.get("decision") == "copied"
        correct = (pnl > 0) if copied else (pnl <= 0)
        _append({
            "type": "outcome", "signal_id": s["signal_id"],
            "ts": int(time.time()), "winner": winner, "won": win,
            "would_be_pnl": round(pnl, 4), "decision": s.get("decision"),
            "skip_reason": s.get("skip_reason"),
            "decision_correct": correct,
            "reward": round(pnl if copied else -pnl, 4),
            "wallet": s.get("wallet"),
        })
        events.append({"event": "shadow_settled",
                       "question": (s.get("question") or "")[:60],
                       "decision": s.get("decision"),
                       "would_be_pnl": round(pnl, 2), "correct": correct})
    return events


def summary():
    signals, outcomes = load_all()
    out = {"signals": len(signals), "graded": len(outcomes),
           "pending": len(signals) - len(outcomes),
           "unevaluable": sum(1 for s in signals.values()
                              if not s.get("evaluable")),
           "by_decision": {}, "skip_reasons": {}, "by_wallet": {}}
    for s in signals.values():
        d = s.get("decision", "?")
        out["by_decision"][d] = out["by_decision"].get(d, 0) + 1
        if d == "skipped":
            r = s.get("skip_reason") or "?"
            out["skip_reasons"][r] = out["skip_reasons"].get(r, 0) + 1
    graded_stats = {}
    for sid, o in outcomes.items():
        s = signals.get(sid, {})
        key = (o.get("decision"), s.get("wallet_name") or
               (o.get("wallet") or "?")[:12])
        g = graded_stats.setdefault(key, {"n": 0, "correct": 0, "pnl": 0.0})
        g["n"] += 1
        g["correct"] += 1 if o.get("decision_correct") else 0
        g["pnl"] = round(g["pnl"] + (o.get("would_be_pnl") or 0), 2)
    for (decision, wallet), g in sorted(graded_stats.items()):
        out["by_wallet"].setdefault(wallet, {})[decision] = {
            "n": g["n"],
            "decision_accuracy": round(g["correct"] / g["n"], 3),
            "would_be_pnl_total": g["pnl"],
        }
    skipped = [o for o in outcomes.values() if o.get("decision") == "skipped"]
    if skipped:
        out["skips_avoided_loss"] = round(
            sum(-o["would_be_pnl"] for o in skipped if o["would_be_pnl"] < 0), 2)
        out["skips_forgone_profit"] = round(
            sum(o["would_be_pnl"] for o in skipped if o["would_be_pnl"] > 0), 2)
        out["skip_decision_accuracy"] = round(
            sum(1 for o in skipped if o["decision_correct"]) / len(skipped), 3)
    copied = [o for o in outcomes.values() if o.get("decision") == "copied"]
    if copied:
        out["copied_would_be_pnl_total"] = round(
            sum(o["would_be_pnl"] for o in copied), 2)
    return out


if __name__ == "__main__":
    print(json.dumps(summary(), indent=1))
