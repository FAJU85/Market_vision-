"""DuckDB schema definition and initialization (Epic A1).

Defines the three core tables (PRD §3.1), the composite index on
``saudi_stocks(symbol, date)`` (SRS §4.2), and the default virtual portfolios.
"""

from __future__ import annotations

import duckdb

# Starting cash for each paper-trading strategy, in SAR.
DEFAULT_STARTING_CASH = 100_000.0
STRATEGY_MODES = ("DAY_TRADING", "SWING_TRADING")

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS saudi_stocks (
    symbol     VARCHAR,
    date       DATE,
    open       DOUBLE,
    high       DOUBLE,
    low        DOUBLE,
    close      DOUBLE,
    adj_close  DOUBLE,
    volume     BIGINT,
    tasi_close DOUBLE,
    brent_price DOUBLE,
    PRIMARY KEY (symbol, date)
);

CREATE TABLE IF NOT EXISTS virtual_portfolio (
    strategy_mode      VARCHAR,
    cash_balance       DOUBLE,
    asset_symbol       VARCHAR,
    shares_held        INTEGER,
    avg_purchase_price DOUBLE,
    last_updated       TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transaction_history (
    transaction_id  UUID PRIMARY KEY,
    timestamp       TIMESTAMP,
    strategy_mode   VARCHAR,
    symbol          VARCHAR,
    type            VARCHAR,
    shares          INTEGER,
    execution_price DOUBLE,
    slippage_paid   DOUBLE,
    commission_paid DOUBLE,
    net_cash_impact DOUBLE
);

CREATE INDEX IF NOT EXISTS idx_ticker_date ON saudi_stocks (symbol, date);
"""


def create_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all tables and indexes if they do not already exist."""
    conn.execute(_SCHEMA_DDL)


def seed_default_portfolios(conn: duckdb.DuckDBPyConnection) -> None:
    """Insert the default per-strategy portfolios when the table is empty."""
    existing = conn.execute("SELECT COUNT(*) FROM virtual_portfolio").fetchone()[0]
    if existing:
        return
    for mode in STRATEGY_MODES:
        conn.execute(
            "INSERT INTO virtual_portfolio VALUES (?, ?, 'CASH', 0, 0.0, NOW())",
            (mode, DEFAULT_STARTING_CASH),
        )


def integrity_ok(conn: duckdb.DuckDBPyConnection) -> bool:
    """Return True if the database is structurally sound.

    The SRS (§5.2) calls for ``PRAGMA integrity_check``, but that is SQLite
    syntax — DuckDB has no equivalent pragma. The DuckDB-appropriate check is to
    confirm every core table is present and fully scannable; corruption in the
    catalog or storage surfaces as a raised exception. Works on both READ_ONLY
    and READ_WRITE connections (WAL merging is handled on writer close).
    """
    try:
        for table in ("saudi_stocks", "virtual_portfolio", "transaction_history"):
            conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    except duckdb.Error:
        return False
    return True
