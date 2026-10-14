"""Tests for the Polymarket fee model. No network."""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

from fees import taker_fee, fee_rate_for, GAS_PER_FILL  # noqa: E402


def live(rate):
    return {"feeSchedule": {"rate": rate, "exponent": 1, "takerOnly": True},
            "feesEnabled": True, "feeType": "sports_fees_v3"}


def test_live_rate_peak():
    # 100 shares @ 50c, sports 0.05 -> 100 * 0.05 * 0.25 = $1.25
    assert taker_fee(100, 0.50, live(0.05)) == 1.25


def test_fee_symmetric_around_half():
    assert taker_fee(100, 0.30, live(0.05)) == pytest.approx(
        taker_fee(100, 0.70, live(0.05)))


def test_fee_shrinks_at_extremes():
    mid = taker_fee(100, 0.50, live(0.05))
    assert taker_fee(100, 0.90, live(0.05)) < mid
    assert taker_fee(100, 0.10, live(0.05)) < mid


def test_fallback_crypto_rate():
    m = {"feesEnabled": True, "feeType": "crypto_fees"}
    assert fee_rate_for(m)[0] == 0.07
    assert taker_fee(100, 0.50, m) == pytest.approx(1.75)


def test_geopolitics_free():
    m = {"feesEnabled": True, "feeType": "geopolitics"}
    assert taker_fee(100, 0.50, m) == 0.0


def test_fees_disabled_market():
    m = {"feesEnabled": False, "feeType": "sports_fees_v3"}
    assert taker_fee(100, 0.50, m) == 0.0


def test_degenerate_inputs_zero():
    assert taker_fee(0, 0.5, live(0.05)) == 0.0
    assert taker_fee(100, 0.0, live(0.05)) == 0.0
    assert taker_fee(100, 1.0, live(0.05)) == 0.0


def test_gas_flat():
    assert GAS_PER_FILL == 0.005
