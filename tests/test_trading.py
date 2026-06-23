"""Tests for the DB-backed single-trade executor (Epic D UI path)."""

from __future__ import annotations

from datetime import date

import pytest

from sqra import db
from sqra.trading import execute_trade


@pytest.fixture()
def conn(tmp_path):
    path = db.initialize(tmp_path / "trade.db")
    with db.writable(path) as c:
        c.execute(
            "INSERT OR REPLACE INTO saudi_stocks VALUES "
            "('1120', ?, 50, 51, 49, 50, 50, 1000, 12000, 82.5)",
            [date(2024, 1, 1)],
        )
        yield c


def test_buy_then_partial_sell(conn):
    buy = execute_trade(
        conn, strategy_mode="DAY_TRADING", symbol="1120", action="BUY",
        capital_allocation=10_000,
    )
    assert buy["status"] == "FILLED"
    bought = buy["shares_held"]
    assert bought > 0

    # Partial sell: only half the position.
    half = bought // 2
    sell = execute_trade(
        conn, strategy_mode="DAY_TRADING", symbol="1120", action="SELL",
        sell_shares=half,
    )
    assert sell["status"] == "FILLED"
    assert sell["shares_held"] == bought - half  # partial position retained


def test_sell_without_position_is_rejected(conn):
    result = execute_trade(
        conn, strategy_mode="SWING_TRADING", symbol="1120", action="SELL",
    )
    assert result["status"] == "NO_POSITION"


def test_unknown_symbol_returns_no_data(conn):
    result = execute_trade(
        conn, strategy_mode="DAY_TRADING", symbol="9999", action="BUY",
        capital_allocation=10_000,
    )
    assert result["status"] == "NO_DATA"


def test_injection_attempt_in_symbol_is_inert(conn):
    # A malicious symbol is rejected by input validation before any query, and
    # the tables remain intact (defense in depth on top of parameterized SQL).
    evil = "1120'); DROP TABLE saudi_stocks;--"
    result = execute_trade(
        conn, strategy_mode="DAY_TRADING", symbol=evil, action="BUY",
        capital_allocation=10_000,
    )
    assert result["status"] == "INVALID_SYMBOL"
    # Table still exists and is queryable.
    assert conn.execute("SELECT COUNT(*) FROM saudi_stocks").fetchone()[0] == 1


def test_label_and_raw_strategy_keys_both_accepted(conn):
    a = execute_trade(
        conn, strategy_mode="Day Trading Core", symbol="1120", action="BUY",
        capital_allocation=5_000,
    )
    assert a["status"] == "FILLED"
