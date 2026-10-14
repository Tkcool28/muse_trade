"""Test isolation: ledger.STATE / ledger.LEDGER are absolute paths to the
LIVE paper-trading state. Every test gets tmp copies instead, so the suite
can never pollute (or read) real state. (2026-10-14: a pytest run wrote test
fills into the live ledger and overwrote state.json — never again.)"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

import ledger  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, "STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(ledger, "LEDGER", str(tmp_path / "ledger.jsonl"))
