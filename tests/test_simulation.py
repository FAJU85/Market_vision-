"""Tests for Epic D1 (event-driven loop) and D3 (trailing stop-loss)."""

from __future__ import annotations

from datetime import date, timedelta

from sqra.simulation import BUY, HOLD, Bar, run_simulation


def _bars(closes, *, highs=None, lows=None, opens=None):
    start = date(2024, 1, 1)
    bars = []
    for i, close in enumerate(closes):
        o = opens[i] if opens else close
        h = highs[i] if highs else max(o, close)
        low = lows[i] if lows else min(o, close)
        bars.append(Bar(start + timedelta(days=i), o, h, low, close))
    return bars


def test_order_decided_on_t_fills_at_open_of_t_plus_1():
    """Done when: a regression test confirms next-day execution (no t leak)."""
    bars = _bars([10, 20, 30], opens=[10, 20, 30])
    seen_lengths = []

    def buy_first_then_hold(history):
        seen_lengths.append(len(history))
        return BUY if len(history) == 1 else HOLD

    result = run_simulation(
        bars, buy_first_then_hold, strategy_mode="DAY_TRADING",
        starting_cash=1_000, capital_per_trade=1_000,
    )
    # Signal on day 0 (history length 1) -> fill at day 1 open (20), not day 0.
    assert result.transactions[0].type == BUY
    assert result.transactions[0].execution_price > 20  # 20 + slippage
    assert result.transactions[0].execution_price < 21
    # The signal never saw more than the bars up to the current day.
    assert seen_lengths == [1, 2, 3]


def test_signal_only_sees_history_up_to_current_bar():
    bars = _bars([10, 11, 12, 13])
    max_seen = {"n": 0}

    def watcher(history):
        max_seen["n"] = max(max_seen["n"], len(history))
        # The last bar in history must never be a future bar.
        assert history[-1].date == bars[len(history) - 1].date
        return HOLD

    run_simulation(bars, watcher)
    assert max_seen["n"] == len(bars)


def test_trailing_stop_liquidates_and_logs():
    """Done when: a stop-loss breach auto-liquidates and logs a SELL."""
    # Buy at day1 open (100), price climbs to 120, then crashes through the
    # -1.5% day-trading trailing stop (120 * 0.985 = 118.2) on day 3; the
    # liquidation fills on day 4's open (next-day execution).
    closes = [100, 100, 120, 110, 108]
    highs = [100, 100, 120, 120, 110]
    lows = [100, 100, 120, 100, 105]  # day 3 low 100 < 118.2 -> breach
    opens = [100, 100, 120, 115, 108]
    bars = _bars(closes, highs=highs, lows=lows, opens=opens)

    def buy_once(history):
        return BUY if len(history) == 1 else HOLD

    result = run_simulation(
        bars, buy_once, strategy_mode="DAY_TRADING",
        starting_cash=100_000, capital_per_trade=100_000,
    )
    types = [t.type for t in result.transactions]
    assert "BUY" in types
    assert "SELL" in types  # trailing stop forced a liquidation
    assert result.portfolio.shares == 0
    # Every transaction carries a UUID.
    assert all(len(t.transaction_id) == 36 for t in result.transactions)
