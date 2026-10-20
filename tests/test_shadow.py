"""Tests for the shadow signal log (engine/shadow.py). No network.

The shadow log grades every copy decision — copied AND skipped — against
the market's real resolution, so a future learner can see the outcomes of
signals we passed on, not just the trades we took (Terry, 2026-10-20).
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

import settle  # noqa: E402
import shadow  # noqa: E402


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(shadow, "SIGNALS", str(tmp_path / "signals.jsonl"))
    monkeypatch.setattr(shadow, "_seen_ids", None)


def _sig(**kw):
    base = {"signal_id": "w1-100-tok1", "wallet": "0xw1",
            "wallet_name": "W1", "act_ts": 100, "token_id": "tok1",
            "condition_id": "0xc1", "market_id": "42", "question": "Q?",
            "side": "Yes", "wallet_price": 0.50, "our_price": 0.50,
            "fee_rate": 0.05, "usd": 5.0, "decision": "skipped",
            "skip_reason": "adverse_move", "evaluable": True}
    base.update(kw)
    return base


def test_would_be_pnl_win_and_loss():
    # $5 @ 0.50 -> 10 shares; fee = 10*0.05*0.5*0.5 + $0.005 gas = $0.13
    assert shadow.would_be_pnl(0.50, True, 0.05) == 10 - 5 - 0.13
    assert shadow.would_be_pnl(0.50, False, 0.05) == -5 - 0.13


def test_would_be_pnl_bad_price():
    assert shadow.would_be_pnl(0, True, 0.05) is None
    assert shadow.would_be_pnl(1.0, True, 0.05) is None
    assert shadow.would_be_pnl(None, True, 0.05) is None


def test_record_signal_dedupes(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert shadow.record_signal(_sig()) is True
    assert shadow.record_signal(_sig()) is False  # crash-retry safe
    signals, outcomes = shadow.load_all()
    assert len(signals) == 1 and outcomes == {}


def test_settle_grades_skipped_signal_correct(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    shadow.record_signal(_sig())
    # Market resolves No; our side was Yes -> copying would have lost, so
    # the skip was CORRECT and the skip reward is the avoided loss.
    monkeypatch.setattr(settle, "market_for", lambda p: {"id": "42"})
    monkeypatch.setattr(settle, "is_resolved", lambda m: "No")
    events = shadow.settle_signals()
    assert len(events) == 1
    _, outcomes = shadow.load_all()
    o = outcomes["w1-100-tok1"]
    assert o["won"] is False and o["would_be_pnl"] < 0
    assert o["decision_correct"] is True
    assert o["reward"] == -o["would_be_pnl"] > 0


def test_settle_grades_copied_signal_and_wrong_skip(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    shadow.record_signal(_sig(signal_id="a-1-t", decision="copied",
                              skip_reason=None))
    shadow.record_signal(_sig(signal_id="a-2-t", decision="skipped",
                              skip_reason="copy_cap"))
    monkeypatch.setattr(settle, "market_for", lambda p: {"id": "42"})
    monkeypatch.setattr(settle, "is_resolved", lambda m: "Yes")
    shadow.settle_signals()
    _, outcomes = shadow.load_all()
    # Winner was Yes = our side: copied decision correct, skip was wrong.
    assert outcomes["a-1-t"]["decision_correct"] is True
    assert outcomes["a-1-t"]["reward"] > 0
    assert outcomes["a-2-t"]["decision_correct"] is False
    assert outcomes["a-2-t"]["reward"] < 0


def test_unevaluable_signal_never_graded(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    shadow.record_signal(_sig(evaluable=False, our_price=None,
                              skip_reason="stale_first_seen"))
    monkeypatch.setattr(settle, "market_for", lambda p: {"id": "42"})
    monkeypatch.setattr(settle, "is_resolved", lambda m: "Yes")
    assert shadow.settle_signals() == []
    assert shadow.pending_signals() == []


def test_summary_counts_decisions(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    shadow.record_signal(_sig())
    shadow.record_signal(_sig(signal_id="x-9-t", decision="copied",
                              skip_reason=None))
    s = shadow.summary()
    assert s["signals"] == 2 and s["graded"] == 0
    assert s["by_decision"] == {"skipped": 1, "copied": 1}
    assert s["skip_reasons"] == {"adverse_move": 1}
