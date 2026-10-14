"""Tests for the paper ledger money math. Prices are mocked; no network."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

import ledger  # noqa: E402

MKT = {"feeSchedule": {"rate": 0.05, "exponent": 1, "takerOnly": True},
       "feesEnabled": True, "feeType": "sports_fees_v3", "endDate": None}


def _mock_prices(buy_px=0.50, sell_px=0.50, mid_px=0.50):
    ledger.clob_price = lambda tid, side: buy_px if side == "BUY" else sell_px
    ledger.clob_midpoint = lambda tid: mid_px


def test_buy_deducts_cost_plus_fee_plus_gas():
    _mock_prices()
    s = ledger.fresh_state()
    pos, err = ledger.buy(s, book="copy", token_id="t1", condition_id="c1",
                          question="Q?", side="Yes", usd=5.0, market=MKT,
                          reason="test")
    assert err is None
    # 10 shares @ .50; fee = 10*.05*.25 = .125; gas .005
    assert pos["shares"] == 10.0
    assert abs(s["cash"] - (200.0 - 5.0 - 0.125 - 0.005)) < 1e-9
    assert abs(s["fees_paid"] - 0.13) < 1e-9


def test_buy_rejects_over_cap():
    _mock_prices()
    s = ledger.fresh_state()
    _, err = ledger.buy(s, book="disc", token_id="t1", condition_id="c1",
                        question="Q?", side="Yes", usd=6.0, market=MKT)
    assert err is not None and "cap" in err


def test_sell_books_realized_net_of_fees():
    _mock_prices(buy_px=0.50, sell_px=0.60)
    s = ledger.fresh_state()
    ledger.buy(s, book="disc", token_id="t1", condition_id="c1",
               question="Q?", side="Yes", usd=5.0, market=MKT)
    # exit fee = 10*.05*.6*.4 = .12 + .005 gas
    r, err = ledger.sell(s, "t1", reason="take profit")
    assert err is None
    # proceeds 6.0 - .125 = 5.875; cost 5.13 -> realized .745
    assert abs(r - (5.875 - 5.13)) < 1e-9
    assert "t1" not in s["positions"]
    assert abs(s["books"]["disc"]["realized"] - r) < 1e-9


def test_settle_win_pays_dollar_per_share():
    _mock_prices()
    s = ledger.fresh_state()
    ledger.buy(s, book="copy", token_id="t1", condition_id="c1",
               question="Q?", side="Yes", usd=5.0, market=MKT)
    r, err = ledger.settle_position(s, "t1", True)
    assert err is None
    assert abs(r - (10.0 - 5.13)) < 1e-9  # no redemption fee


def test_settle_loss_zeroes():
    _mock_prices()
    s = ledger.fresh_state()
    ledger.buy(s, book="copy", token_id="t1", condition_id="c1",
               question="Q?", side="Yes", usd=5.0, market=MKT)
    r, _ = ledger.settle_position(s, "t1", False)
    assert abs(r - (-5.13)) < 1e-9


def test_sweep_moves_25_chunks():
    _mock_prices()
    s = ledger.fresh_state()
    s["realized_pnl"] = 30.0
    swept = ledger.sweep_check(s)
    assert swept == [25.0]
    assert s["sweep"] == 25.0 and s["swept_total"] == 25.0
    assert s["cash"] == 175.0


def test_drawdown_halt():
    _mock_prices()
    s = ledger.fresh_state()
    s["cash"] = 150.0  # equity < 160
    assert ledger.check_halt(s) is True
    assert s["halted"] is True
    _, err = ledger.buy(s, book="disc", token_id="t9", condition_id="c9",
                        question="Q?", side="Yes", usd=5.0, market=MKT)
    assert err is not None and "halted" in err


def test_no_double_spend_same_token_merges():
    _mock_prices()
    s = ledger.fresh_state()
    ledger.buy(s, book="copy", token_id="t1", condition_id="c1",
               question="Q?", side="Yes", usd=5.0, market=MKT)
    pos, err = ledger.buy(s, book="copy", token_id="t1", condition_id="c1",
                          question="Q?", side="Yes", usd=5.0, market=MKT)
    assert err is None
    assert pos["shares"] == 20.0  # merged, not duplicated
