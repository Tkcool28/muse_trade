"""Tests for copy-trading guards. No network."""
import importlib.util
import os
import time

import pytest

_engine = os.path.join(os.path.dirname(__file__), "..", "engine", "copy.py")
_spec = importlib.util.spec_from_file_location("poly_copy", _engine)
_poly_copy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_poly_copy)
token_side = _poly_copy.token_side


def _market(yes_tok="1", no_tok="2"):
    return {"clobTokenIds": f'["{yes_tok}", "{no_tok}"]'}


def test_token_side_yes():
    assert token_side(_market(), "1") == "Yes"


def test_token_side_no():
    assert token_side(_market(), "2") == "No"


def test_token_side_unknown_token_is_none():
    # 2026-10-14: a foreign token defaulted to "No" and was filled with the
    # wrong market's metadata. Unknown tokens must fail closed.
    assert token_side(_market(), "999") is None


def test_token_side_empty_tokens_is_none():
    assert token_side({"clobTokenIds": "[]"}, "1") is None
    assert token_side({}, "1") is None


# --- 30-day resolution cap on copy entries (Terry, 2026-10-23) ---

def _mkt(days=None, end=None):
    if end is None:
        end = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                            time.gmtime(time.time() + days * 86400))
    return {"clobTokenIds": '["1", "2"]', "closed": False,
            "question": "Test market", "id": "999", "endDate": end}


_W = {"address": "0x" + "a" * 40, "name": "TestWallet"}
_ACT = {"token_id": "1", "condition_id": "0xcond", "price": 0.50,
        "timestamp": int(time.time())}


@pytest.fixture
def _patched(monkeypatch):
    calls = []
    monkeypatch.setattr(_poly_copy, "clob_price", lambda tid, side: 0.5)
    monkeypatch.setattr(_poly_copy, "book_depth_ok", lambda *a, **k: True)

    def fake_buy(s, **kw):
        calls.append(kw)
        return {"token_id": kw["token_id"]}, None

    monkeypatch.setattr(_poly_copy, "buy", fake_buy)
    return calls


def test_copy_skips_market_resolving_over_30d(monkeypatch, _patched):
    monkeypatch.setattr(_poly_copy, "market_for", lambda cond: _mkt(45))
    ok, payload = _poly_copy.try_copy_buy({"positions": {}}, dict(_W), _ACT)
    assert not ok
    assert payload["signal"]["skip_reason"] == "long_resolution"
    assert _patched == []  # no fill attempted


def test_copy_allows_market_within_30d(monkeypatch, _patched):
    monkeypatch.setattr(_poly_copy, "market_for", lambda cond: _mkt(10))
    ok, payload = _poly_copy.try_copy_buy({"positions": {}}, dict(_W), _ACT)
    assert ok
    assert len(_patched) == 1


def test_copy_unparseable_enddate_fails_open(monkeypatch, _patched):
    # Oct-14 lesson: a garbage/missing endDate must never block the book;
    # the 21-day time stop is the backstop on capital tie-up.
    monkeypatch.setattr(_poly_copy, "market_for",
                        lambda cond: _mkt(end=""))
    ok, payload = _poly_copy.try_copy_buy({"positions": {}}, dict(_W), _ACT)
    assert ok
    assert len(_patched) == 1
