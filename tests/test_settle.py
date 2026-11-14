"""Tests for settlement market resolution. No network.

2026-10-17: Gamma's /markets?condition_ids= listing HIDES resolved markets
(returns []), while /markets/{id} returns them with full umaResolutionStatus.
Positions sat open for 2 days showing mark 1.00 because settle.py only used
the condition_ids listing. market_for() must prefer the stored market id.
"""
import importlib.util
import json
import os

_engine = os.path.join(os.path.dirname(__file__), "..", "engine", "settle.py")
_spec = importlib.util.spec_from_file_location("poly_settle", _engine)
settle = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(settle)


def _resolved_market(winner):
    # winner: "Yes" -> ["1","0"], "No" -> ["0","1"]
    ops = ["1", "0"] if winner == "Yes" else ["0", "1"]
    return {"id": "123", "closed": True, "umaResolutionStatus": "resolved",
            "outcomePrices": json.dumps(ops)}


def test_market_for_prefers_market_id(monkeypatch):
    calls = []
    monkeypatch.setattr(
        settle, "gamma_market_by_id",
        lambda mid: calls.append(("by_id", mid)) or _resolved_market("Yes"))
    monkeypatch.setattr(
        settle, "gamma_market_by_condition",
        lambda cond: calls.append(("by_cond", cond)) or {"id": "999"})
    p = {"market_id": "123", "condition_id": "0xabc"}
    m = settle.market_for(p)
    assert m["umaResolutionStatus"] == "resolved"
    assert calls == [("by_id", "123")], f"must not touch condition listing: {calls}"


def test_market_for_falls_back_to_condition(monkeypatch):
    calls = []
    monkeypatch.setattr(
        settle, "gamma_market_by_id",
        lambda mid: calls.append(("by_id", mid)) or (_ for _ in ()).throw(
            RuntimeError("nope")))
    monkeypatch.setattr(
        settle, "gamma_market_by_condition",
        lambda cond: calls.append(("by_cond", cond)) or _resolved_market("No"))
    p = {"condition_id": "0xabc"}  # no market_id (old position)
    m = settle.market_for(p)
    assert settle.is_resolved(m) == "No"
    assert ("by_cond", "0xabc") in calls


def test_market_for_by_id_falls_back_on_missing(monkeypatch):
    # by-id returns None (unknown id) -> condition listing is tried
    monkeypatch.setattr(settle, "gamma_market_by_id", lambda mid: None)
    monkeypatch.setattr(
        settle, "gamma_market_by_condition",
        lambda cond: _resolved_market("Yes"))
    m = settle.market_for({"market_id": "nope", "condition_id": "0xabc"})
    assert settle.is_resolved(m) == "Yes"


def test_is_resolved_requires_uma_resolved():
    assert settle.is_resolved(
        {"closed": True, "umaResolutionStatus": "proposed",
         "outcomePrices": '["1","0"]'}) is None
    assert settle.is_resolved(
        {"closed": False, "umaResolutionStatus": "resolved",
         "outcomePrices": '["1","0"]'}) is None


def test_is_resolved_yes_and_no():
    assert settle.is_resolved(_resolved_market("Yes")) == "Yes"
    assert settle.is_resolved(_resolved_market("No")) == "No"


def test_is_resolved_ignores_split():
    # A 0.5/0.5 split is NOT a clean win for either side — it must fall
    # through to split_payout, not resolve as a win/loss.
    m = {"closed": True, "umaResolutionStatus": "resolved",
         "outcomePrices": '["0.5","0.5"]'}
    assert settle.is_resolved(m) is None


# --- split-resolution settle (Terry, 2026-11-14) ---

def _split_market(ops):
    return {"id": "5533029", "closed": True,
            "umaResolutionStatus": "resolved",
            "outcomePrices": json.dumps(ops)}


def test_split_payout_half_half():
    m = _split_market(["0.5", "0.5"])
    assert settle.split_payout(m, "Yes") == 0.5
    assert settle.split_payout(m, "No") == 0.5


def test_split_payout_other_fraction():
    m = _split_market(["0.25", "0.75"])
    assert settle.split_payout(m, "Yes") == 0.25
    assert settle.split_payout(m, "No") == 0.75


def test_split_payout_rejects_non_splits():
    assert settle.split_payout(_resolved_market("Yes"), "Yes") is None
    assert settle.split_payout(_resolved_market("No"), "No") is None
    assert settle.split_payout(
        {"closed": True, "umaResolutionStatus": "proposed",
         "outcomePrices": '["0.5","0.5"]'}, "Yes") is None
    assert settle.split_payout(
        {"closed": False, "umaResolutionStatus": "resolved",
         "outcomePrices": '["0.5","0.5"]'}, "Yes") is None
    assert settle.split_payout(
        _split_market(["0.5", "0.5", "0.0"]), "Yes") is None
    assert settle.split_payout(
        _split_market(["abc", "0.5"]), "Yes") is None
    assert settle.split_payout(None, "Yes") is None


def test_run_settle_closes_split_position(monkeypatch):
    # End-to-end: a 0.5/0.5 market settles the West Indies-style position
    # at half value through the real ledger math (no network).
    import ledger
    s = ledger.fresh_state()
    s["positions"]["t1"] = {
        "condition_id": "c1", "question": "West Indies Tour of India T20s",
        "side": "Yes", "shares": 10.0, "avg_price": 0.5, "cost": 5.13,
        "last_price": 0.505, "book": "copy", "opened_ts": 0,
        "reason": "test", "wallet": None, "market_id": "5533029"}
    monkeypatch.setattr(settle, "market_for",
                        lambda p: _split_market(["0.5", "0.5"]))
    monkeypatch.setattr(settle, "check_halt", lambda s: False)
    monkeypatch.setattr(settle, "sweep_check", lambda s: [])
    evs = settle.run_settle(s)
    assert "t1" not in s["positions"]
    assert abs(s["realized_pnl"] - (5.0 - 5.13)) < 1e-9
    assert len(evs) == 1 and evs[0]["event"] == "settled"
    assert evs[0]["split"] == 0.5
    assert abs(evs[0]["realized"] - (-0.13)) < 1e-9
