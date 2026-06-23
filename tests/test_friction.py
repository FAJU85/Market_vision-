"""Tests for Epic D2 — friction model formulas."""

from __future__ import annotations

import pytest

from sqra import friction


def test_buy_slippage_inflates_price():
    assert friction.buy_execution_price(100.0) == pytest.approx(100.10)


def test_sell_slippage_deflates_price():
    assert friction.sell_execution_price(100.0) == pytest.approx(99.90)


def test_commission_is_0_155_percent():
    assert friction.commission(10_000.0) == pytest.approx(15.5)


def test_round_trip_friction_is_0_51_percent():
    assert friction.ROUND_TRIP_FRICTION == pytest.approx(0.0051)


def test_signal_below_friction_is_not_actionable():
    assert friction.is_actionable(0.004) is False  # 0.4% < 0.51%
    assert friction.is_actionable(0.006) is True   # 0.6% >= 0.51%


def test_stop_loss_prices_per_strategy():
    assert friction.stop_loss_price(100.0, "DAY_TRADING") == pytest.approx(98.5)
    assert friction.stop_loss_price(100.0, "SWING_TRADING") == pytest.approx(95.0)


def test_unknown_strategy_raises():
    with pytest.raises(ValueError):
        friction.stop_loss_price(100.0, "NOPE")
