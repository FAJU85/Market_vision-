"""Tests for Epic E3 — performance KPI math."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from sqra.kpis import (
    daily_returns,
    max_drawdown,
    round_trip_pnls,
    sharpe_ratio,
    win_loss_ratio,
)


def test_daily_returns():
    assert daily_returns([100, 110, 99]) == pytest.approx([0.1, -0.1])


def test_sharpe_positive_for_steady_growth():
    curve = [100 * (1.01**i) for i in range(30)]  # steady +1% per period
    assert sharpe_ratio(curve) > 0


def test_sharpe_zero_for_flat_curve():
    assert sharpe_ratio([100, 100, 100, 100]) == 0.0


def test_sharpe_zero_with_insufficient_data():
    assert sharpe_ratio([100]) == 0.0


def test_max_drawdown_captures_peak_to_trough():
    # Peak 120, trough 60 -> -50%.
    curve = [100, 120, 90, 60, 80]
    assert max_drawdown(curve) == pytest.approx(-0.5)


def test_max_drawdown_zero_for_monotonic_increase():
    assert max_drawdown([100, 110, 120]) == 0.0


def test_win_loss_ratio():
    assert win_loss_ratio([10, -5, 20, -1]) == 0.5
    assert win_loss_ratio([]) == 0.0


@dataclass
class _Txn:
    type: str
    net_cash_impact: float


def test_round_trip_pnls_pairs_buys_and_sells():
    txns = [
        _Txn("BUY", -1000.0),
        _Txn("SELL", 1200.0),   # +200 win
        _Txn("BUY", -500.0),
        _Txn("SELL", 400.0),    # -100 loss
    ]
    pnls = round_trip_pnls(txns)
    assert pnls == pytest.approx([200.0, -100.0])
    assert win_loss_ratio(pnls) == 0.5


def test_round_trip_ignores_unclosed_position():
    txns = [_Txn("BUY", -1000.0)]
    assert round_trip_pnls(txns) == []
