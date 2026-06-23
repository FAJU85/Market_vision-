"""Tests for Epic A — Foundation & Storage."""

from __future__ import annotations

import duckdb
import pytest

from sqra import db
from sqra.schema import DEFAULT_STARTING_CASH, STRATEGY_MODES, integrity_ok


@pytest.fixture()
def db_path(tmp_path):
    """A freshly initialized SQRA database in a temp directory."""
    return db.initialize(tmp_path / "sqra_storage.db")


# --- A1: schema + init, integrity check ------------------------------------


def test_fresh_db_boots_and_integrity_passes(db_path):
    """Done when: a fresh DB boots and PRAGMA integrity_check returns ok."""
    assert db_path.exists()
    with db.read_only(db_path) as conn:
        assert integrity_ok(conn)


def test_core_tables_exist(db_path):
    with db.read_only(db_path) as conn:
        tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    assert {"saudi_stocks", "virtual_portfolio", "transaction_history"} <= tables


def test_default_portfolios_seeded_once(db_path):
    with db.read_only(db_path) as conn:
        rows = conn.execute(
            "SELECT strategy_mode, cash_balance FROM virtual_portfolio ORDER BY strategy_mode"
        ).fetchall()
    assert {r[0] for r in rows} == set(STRATEGY_MODES)
    assert all(r[1] == DEFAULT_STARTING_CASH for r in rows)

    # Re-initializing must not duplicate the seed rows.
    db.initialize(db_path)
    with db.read_only(db_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM virtual_portfolio").fetchone()[0]
    assert count == len(STRATEGY_MODES)


# --- A2: connection-mode discipline ----------------------------------------


def test_writer_then_reader_handoff(db_path):
    """Done when: after a short-lived writer closes (checkpointing the WAL), a
    READ_ONLY connection sees the committed data.

    DuckDB takes an exclusive lock for a READ_WRITE connection, so the design
    keeps the writer short-lived and hands off to readers sequentially (SRS
    §2.2; Blueprint §III flags true concurrency as a production risk).
    """
    with db.writable(db_path) as writer:
        writer.execute(
            "INSERT INTO saudi_stocks VALUES "
            "('1120', DATE '2024-01-01', 1, 2, 0.5, 1.5, 1.5, 1000, 12000, 82.5)"
        )
    with db.read_only(db_path) as reader:
        count = reader.execute(
            "SELECT COUNT(*) FROM saudi_stocks WHERE symbol = '1120'"
        ).fetchone()[0]
    assert count == 1


def test_multiple_readers_coexist(db_path):
    """The UI path opens several READ_ONLY connections; these must coexist."""
    with db.read_only(db_path) as reader_a, db.read_only(db_path) as reader_b:
        assert reader_a.execute("SELECT 1").fetchone()[0] == 1
        assert reader_b.execute("SELECT COUNT(*) FROM virtual_portfolio").fetchone()[0] == 2


def test_read_only_connection_rejects_writes(db_path):
    with db.read_only(db_path) as reader:
        with pytest.raises(duckdb.Error):
            reader.execute(
                "INSERT INTO saudi_stocks VALUES "
                "('2222', DATE '2024-01-02', 1, 2, 0.5, 1.5, 1.5, 1000, 12000, 82.5)"
            )
