"""Tests for Epic F — hardening (recovery + input validation)."""

from __future__ import annotations

import pytest

from sqra import db
from sqra.schema import integrity_ok
from sqra.trading import execute_trade, is_valid_symbol

# --- F1: startup integrity check + schema recovery -------------------------


def test_recovery_recreates_schema_from_corrupt_file(tmp_path):
    """Done when: a corrupted DB file recovers cleanly into a usable state."""
    path = tmp_path / "sqra_storage.db"
    path.write_bytes(b"this is not a valid duckdb file" * 100)

    recovered = db.initialize_with_recovery(path)

    assert recovered == path
    assert path.with_suffix(".db.corrupt").exists()  # corrupt file quarantined
    with db.read_only(path) as conn:
        assert integrity_ok(conn)
        # Default portfolios were re-seeded.
        assert conn.execute("SELECT COUNT(*) FROM virtual_portfolio").fetchone()[0] == 2


def test_recovery_is_noop_on_healthy_db(tmp_path):
    path = db.initialize(tmp_path / "healthy.db")
    db.initialize_with_recovery(path)
    assert not path.with_suffix(".db.corrupt").exists()


# --- F2: input validation on trade parameters ------------------------------


@pytest.mark.parametrize(
    "symbol,valid",
    [("1120", True), ("AAPL", True), ("", False), ("a b", False),
     ("1120'; DROP TABLE x;--", False), ("x" * 20, False)],
)
def test_symbol_validation(symbol, valid):
    assert is_valid_symbol(symbol) is valid


def test_buy_with_non_positive_capital_is_rejected(tmp_path):
    path = db.initialize(tmp_path / "v.db")
    with db.writable(path) as conn:
        result = execute_trade(
            conn, strategy_mode="DAY_TRADING", symbol="1120", action="BUY",
            capital_allocation=0,
        )
    assert result["status"] == "INVALID_CAPITAL"
