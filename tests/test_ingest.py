"""Tests for Epic B1 — ingestion pipeline and cron guard."""

from __future__ import annotations

from datetime import date

import pytest

import backend_cron
from sqra import db
from sqra.ingest import MockProvider, ingest_market_data


@pytest.fixture()
def db_path(tmp_path):
    return db.initialize(tmp_path / "sqra_storage.db")


def test_ingest_upserts_for_many_symbols(db_path):
    """Done when: rows are upserted for >=200 symbols."""
    symbols = [str(1000 + i) for i in range(200)]
    with db.writable(db_path) as conn:
        written = ingest_market_data(conn, MockProvider(), symbols, lookback=30)
    assert written == 200 * 30
    with db.read_only(db_path) as conn:
        distinct = conn.execute("SELECT COUNT(DISTINCT symbol) FROM saudi_stocks").fetchone()[0]
    assert distinct == 200


def test_upsert_is_idempotent(db_path):
    symbols = ["1120", "2222"]
    with db.writable(db_path) as conn:
        ingest_market_data(conn, MockProvider(), symbols, lookback=30)
    with db.writable(db_path) as conn:
        ingest_market_data(conn, MockProvider(), symbols, lookback=30)
    with db.read_only(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM saudi_stocks").fetchone()[0]
    assert total == 2 * 30  # replaced, not duplicated


def test_cron_skips_non_trading_day(db_path, monkeypatch):
    """Done when: a holiday/weekend run exits without writing."""
    monkeypatch.setattr(db, "DB_PATH", db_path, raising=False)
    saturday = date(2024, 1, 6)
    rows = backend_cron.run(today=saturday, provider=MockProvider(), symbols=["1120"])
    assert rows == 0


def test_cron_ingests_on_trading_day(tmp_path, monkeypatch):
    target_db = tmp_path / "cron.db"
    monkeypatch.setattr(backend_cron.db, "DB_PATH", target_db, raising=False)
    monkeypatch.setattr("sqra.config.DB_PATH", target_db, raising=False)
    sunday = date(2024, 1, 7)
    rows = backend_cron.run(today=sunday, provider=MockProvider(), symbols=["1120", "2222"])
    assert rows > 0
