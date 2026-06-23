"""Event-driven paper-trading simulation (Epic D1 + D3).

A strict, row-by-row loop over chronological bars (PRD §5.2 / SRS §3.3). Two
rules guarantee no look-ahead leakage:

* A signal function on day ``t`` receives only bars ``[0 .. t]``.
* An order decided on day ``t`` fills at the **open of day ``t + 1``**
  (next-day execution), never the same bar.

A trailing stop-loss is monitored each bar against the position's peak; a breach
queues a liquidation that, like every order, fills on the next bar's open. Every
fill is logged as a :class:`Transaction` with a UUID (SRS §3.3.3).

Vectorized backtesting is intentionally avoided so information cannot leak from
step ``t + 1`` back to ``t``.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from .friction import (
    NO_ACTION,
    buy_execution_price,
    commission,
    sell_execution_price,
    stop_loss_price,
)

BUY, SELL, HOLD = "BUY", "SELL", "HOLD"


@dataclass(frozen=True)
class Bar:
    date: date
    open: float
    high: float
    low: float
    close: float


@dataclass
class Transaction:
    transaction_id: str
    timestamp: date
    strategy_mode: str
    type: str
    shares: int
    execution_price: float
    slippage_paid: float
    commission_paid: float
    net_cash_impact: float


@dataclass
class Portfolio:
    cash: float
    shares: int = 0
    avg_price: float = 0.0
    peak_price: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.shares > 0


@dataclass
class SimulationResult:
    transactions: list[Transaction] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    portfolio: Portfolio | None = None


# A signal sees only history up to and including the current bar.
SignalFn = Callable[[list[Bar]], str]


def _execute_buy(
    pf: Portfolio, bar: Bar, strategy_mode: str, capital_per_trade: float
) -> Transaction | None:
    mid = bar.open
    exec_price = buy_execution_price(mid)
    budget = min(capital_per_trade, pf.cash)
    shares = int(budget // exec_price)
    # Shrink until gross + commission fits the available cash.
    while shares > 0 and shares * exec_price + commission(shares * exec_price) > pf.cash:
        shares -= 1
    if shares <= 0:
        return None
    gross = shares * exec_price
    comm = commission(gross)
    total_cost = gross + comm
    pf.avg_price = (pf.shares * pf.avg_price + gross) / (pf.shares + shares)
    pf.shares += shares
    pf.cash -= total_cost
    pf.peak_price = max(pf.peak_price, mid)
    return Transaction(
        transaction_id=str(uuid.uuid4()),
        timestamp=bar.date,
        strategy_mode=strategy_mode,
        type=BUY,
        shares=shares,
        execution_price=exec_price,
        slippage_paid=shares * (exec_price - mid),
        commission_paid=comm,
        net_cash_impact=-total_cost,
    )


def _execute_sell(pf: Portfolio, bar: Bar, strategy_mode: str) -> Transaction | None:
    if not pf.is_open:
        return None
    mid = bar.open
    shares = pf.shares
    exec_price = sell_execution_price(mid)
    gross = shares * exec_price
    comm = commission(gross)
    net = gross - comm
    pf.cash += net
    pf.shares = 0
    pf.avg_price = 0.0
    pf.peak_price = 0.0
    return Transaction(
        transaction_id=str(uuid.uuid4()),
        timestamp=bar.date,
        strategy_mode=strategy_mode,
        type=SELL,
        shares=shares,
        execution_price=exec_price,
        slippage_paid=shares * (mid - exec_price),
        commission_paid=comm,
        net_cash_impact=net,
    )


def run_simulation(
    bars: list[Bar],
    signal_fn: SignalFn,
    *,
    strategy_mode: str = "DAY_TRADING",
    starting_cash: float = 100_000.0,
    capital_per_trade: float = 10_000.0,
) -> SimulationResult:
    """Run the event-driven simulation and return transactions + equity curve."""
    pf = Portfolio(cash=starting_cash)
    result = SimulationResult(portfolio=pf)
    pending: str | None = None  # action queued on day t, filled on day t+1

    for t, bar in enumerate(bars):
        # 1. Fill any order queued on the previous bar, at today's open.
        if pending == BUY and not pf.is_open:
            txn = _execute_buy(pf, bar, strategy_mode, capital_per_trade)
            if txn:
                result.transactions.append(txn)
        elif pending == SELL and pf.is_open:
            txn = _execute_sell(pf, bar, strategy_mode)
            if txn:
                result.transactions.append(txn)
        pending = None

        # 2. While holding, update the peak and check the trailing stop.
        if pf.is_open:
            pf.peak_price = max(pf.peak_price, bar.high)
            stop = stop_loss_price(pf.peak_price, strategy_mode)
            if bar.low <= stop:
                pending = SELL  # liquidate on next bar's open

        # 3. Otherwise, ask the signal for an action on history [0..t].
        if pending is None:
            action = signal_fn(bars[: t + 1])
            if action in (BUY, SELL):
                pending = action

        # 4. Mark-to-market equity at today's close.
        result.equity_curve.append(pf.cash + pf.shares * bar.close)

    return result


def hold(_history: list[Bar]) -> str:
    """A no-op signal (always HOLD); useful for tests."""
    return HOLD


# Re-export for callers that suppress sub-threshold signals.
__all__ = [
    "Bar", "Transaction", "Portfolio", "SimulationResult",
    "run_simulation", "hold", "NO_ACTION", "BUY", "SELL", "HOLD",
]
