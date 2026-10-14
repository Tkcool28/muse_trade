#!/usr/bin/env python3
"""Candidate scanner: new markets, niche markets, cross-market structure gaps.

Output -> state/candidates.json, consumed by Muse's 2x-daily discretionary
sessions. The scanner surfaces; the LLM decides.
"""
import json
import os
import time

from pm_api import gamma_markets

ROOT = os.path.expanduser("~/workspace/poly-llm")
CAND = os.path.join(ROOT, "state", "candidates.json")

NEW_HOURS = 12
NICHE_VOL_CAP = 10000.0
SUM_LOW, SUM_HIGH = 0.85, 1.15


def _prices(m):
    try:
        return [float(x) for x in json.loads(m.get("outcomePrices") or "[]")]
    except (ValueError, TypeError):
        return []


def _brief(m):
    tids = []
    try:
        tids = json.loads(m.get("clobTokenIds") or "[]")
    except (ValueError, TypeError):
        pass
    pr = _prices(m)
    return {
        "question": m.get("question", ""),
        "condition_id": m.get("conditionId", ""),
        "token_yes": str(tids[0]) if len(tids) > 0 else None,
        "token_no": str(tids[1]) if len(tids) > 1 else None,
        "yes_price": pr[0] if len(pr) > 0 else None,
        "no_price": pr[1] if len(pr) > 1 else None,
        "volume": float(m.get("volume") or m.get("volumeNum") or 0),
        "liquidity": float(m.get("liquidity") or m.get("liquidityNum") or 0),
        "end_date": m.get("endDate"),
        "start_date": m.get("startDate"),
        "fee_type": m.get("feeType"),
        "event_id": (m.get("events") or [{}])[0].get("id"),
        "event_title": (m.get("events") or [{}])[0].get("title"),
    }


def scan():
    try:
        newest = gamma_markets({"closed": "false", "limit": 100,
                                "order": "startDate", "ascending": "false"})
        niche_pull = gamma_markets({"closed": "false", "limit": 100,
                                    "volume_num_max": NICHE_VOL_CAP})
    except RuntimeError:
        return {"generated_ts": int(time.time()), "error": "gamma fetch failed",
                "new_markets": [], "niche": [], "cross_market": []}
    now = time.time()
    new, niche, by_event = [], [], {}
    seen = set()
    for m in newest:
        b = _brief(m)
        try:
            age_h = (now - time.mktime(time.strptime(
                (m.get("startDate") or "")[:19], "%Y-%m-%dT%H:%M:%S"))) / 3600
        except (ValueError, TypeError):
            age_h = 999
        b["age_h"] = round(age_h, 1)
        if 0 <= age_h <= NEW_HOURS and (b["liquidity"] or 0) > 500:
            new.append(b)
            seen.add(b["condition_id"])
    for m in niche_pull:
        b = _brief(m)
        if b["condition_id"] in seen:
            continue
        if (b["liquidity"] or 0) > 200:
            niche.append(b)
            seen.add(b["condition_id"])
    for b in new + niche:
        eid = b["event_id"]
        if eid:
            by_event.setdefault(eid, []).append(b)
    new.sort(key=lambda b: -(b["liquidity"] or 0))
    niche.sort(key=lambda b: -(b["volume"] or 0))

    cross = []
    for eid, ms_ in by_event.items():
        if len(ms_) < 3:
            continue
        s = sum(b["yes_price"] or 0 for b in ms_)
        if s < SUM_LOW or s > SUM_HIGH:
            cross.append({
                "event": ms_[0]["event_title"], "event_id": eid,
                "n_markets": len(ms_), "yes_sum": round(s, 3),
                "markets": [{"question": b["question"][:70],
                             "yes": b["yes_price"],
                             "token_yes": b["token_yes"],
                             "condition_id": b["condition_id"]}
                            for b in ms_[:6]],
                "note": ("implied Yes probs sum to %.2f — structure gap "
                         "if outcomes are mutually exclusive" % s),
            })
    out = {"generated_ts": int(now),
           "new_markets": new[:15], "niche": niche[:15],
           "cross_market": cross[:10]}
    with open(CAND, "w") as f:
        json.dump(out, f, indent=1)
    return out


if __name__ == "__main__":
    print(json.dumps({k: (len(v) if isinstance(v, list) else v)
                      for k, v in scan().items()}, indent=1))
