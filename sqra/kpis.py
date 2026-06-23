"""Performance KPIs for the dashboard (Epic E3).

Pure functions over an equity curve and a list of trade results, so each metric
is unit-tested without any UI dependency:

* **Sharpe ratio** — annualized risk-adjusted return.
* **Maximum drawdown** — largest peak-to-trough equity decline.
* **Win/Loss ratio** — fraction of round-trip trades that were profitable
  after friction.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

TRADING_DAYS_PER_YEAR = 252


def daily_returns(equity_curve: Sequence[float]) -> list[float]:
    """Simple period-over-period returns from an equity curve."""
    returns = []
    for prev, curr in zip(equity_curve[:-1], equity_curve[1:], strict=True):
        if prev != 0:
            returns.append((curr - prev) / prev)
    return returns


def sharpe_ratio(
    equity_curve: Sequence[float],
    *,
    risk_free_rate: float = 0.0,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualized Sharpe ratio. Returns 0.0 when volatility is undefined."""
    returns = daily_returns(equity_curve)
    if len(returns) < 2:
        return 0.0
    rf_per_period = risk_free_rate / periods_per_year
    excess = [r - rf_per_period for r in returns]
    mean = sum(excess) / len(excess)
    variance = sum((r - mean) ** 2 for r in excess) / (len(excess) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(periods_per_year)


def max_drawdown(equity_curve: Sequence[float]) -> float:
    """Largest peak-to-trough decline as a non-positive fraction (e.g. -0.42)."""
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    worst = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            drawdown = (value - peak) / peak
            worst = min(worst, drawdown)
    return worst


def win_loss_ratio(trade_pnls: Sequence[float]) -> float:
    """Fraction of trades with positive PnL. Returns 0.0 with no trades."""
    if not trade_pnls:
        return 0.0
    wins = sum(1 for pnl in trade_pnls if pnl > 0)
    return wins / len(trade_pnls)


def round_trip_pnls(transactions: Sequence) -> list[float]:
    """Net PnL per closed round trip, after friction.

    Pairs each BUY's cash impact (negative) with the subsequent SELL's proceeds
    (positive); the sum is the realized PnL of that round trip. Transactions must
    expose ``type`` and ``net_cash_impact`` attributes and be in chronological
    order.
    """
    pnls: list[float] = []
    open_cost = 0.0
    holding = False
    for txn in transactions:
        if txn.type == "BUY":
            open_cost += txn.net_cash_impact  # negative
            holding = True
        elif txn.type == "SELL" and holding:
            pnls.append(open_cost + txn.net_cash_impact)
            open_cost = 0.0
            holding = False
    return pnls
