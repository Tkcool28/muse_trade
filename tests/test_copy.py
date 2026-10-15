"""Tests for copy-trading guards. No network."""
import importlib.util
import os

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
