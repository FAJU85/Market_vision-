"""Post-market data ingestion engine (Epic B1).

Fetches adjusted EOD bars for Tadawul equities plus the TASI index and Brent
crude macro node, applies the outlier defense, and upserts into ``saudi_stocks``
(PRD §4.1 / SRS §3.1).

The data source is abstracted behind :class:`MarketDataProvider` so a real
provider (e.g. Tadawul/Yahoo) can be slotted in without touching the ingestion
or storage logic. A deterministic :class:`MockProvider` is included for tests
and offline development.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

import duckdb
import numpy as np
import pandas as pd

from .outliers import apply_outlier_defense

# Canonical column order matching the saudi_stocks schema.
BAR_COLUMNS = [
    "symbol",
    "date",
    "open",
    "high",
    "low",
    "close",
    "adj_close",
    "volume",
    "tasi_close",
    "brent_price",
]


class MarketDataProvider(Protocol):
    """Fetches raw EOD bars for a set of symbols."""

    def fetch_eod(self, symbols: list[str], lookback: int) -> pd.DataFrame:
        """Return a DataFrame with at least the columns in ``BAR_COLUMNS``."""
        ...


class MockProvider:
    """Deterministic synthetic provider for tests and offline runs.

    Produces a reproducible random walk per symbol so ingestion can be exercised
    without external network access.
    """

    def __init__(self, seed: int = 42) -> None:
        self._seed = seed

    def fetch_eod(self, symbols: list[str], lookback: int = 200) -> pd.DataFrame:
        dates = pd.date_range(end=datetime.now(), periods=lookback, freq="B")
        records: list[dict] = []
        for offset, symbol in enumerate(symbols):
            rng = np.random.default_rng(self._seed + offset)
            base = 100.0
            for day in dates:
                base *= 1 + rng.normal(0, 0.02)
                close = round(base, 4)
                records.append(
                    {
                        "symbol": symbol,
                        "date": day.date(),
                        "open": round(close * rng.uniform(0.99, 1.01), 4),
                        "high": round(close * rng.uniform(1.00, 1.03), 4),
                        "low": round(close * rng.uniform(0.97, 1.00), 4),
                        "close": close,
                        "adj_close": close,
                        "volume": int(rng.uniform(100_000, 2_000_000)),
                        "tasi_close": round(12_000.0 * rng.uniform(0.99, 1.01), 4),
                        "brent_price": round(82.5 * rng.uniform(0.98, 1.02), 4),
                    }
                )
        return pd.DataFrame.from_records(records)


def clean_bars(raw: pd.DataFrame) -> pd.DataFrame:
    """Apply the outlier defense per symbol and return cleaned, ordered bars.

    ``adj_close`` defaults to ``close`` when the provider does not supply it.
    """
    if "adj_close" not in raw.columns:
        raw = raw.assign(adj_close=raw["close"])

    cleaned = [
        apply_outlier_defense(group, symbol=symbol)
        for symbol, group in raw.groupby("symbol", sort=False)
    ]
    result = pd.concat(cleaned, ignore_index=True)
    return result[BAR_COLUMNS]


def upsert_bars(conn: duckdb.DuckDBPyConnection, bars: pd.DataFrame) -> int:
    """Insert-or-replace cleaned bars into ``saudi_stocks``; return row count.

    Uses a registered relation rather than string interpolation, so no value is
    ever spliced into SQL (CLAUDE.md §1.3 input validation).
    """
    ordered = bars[BAR_COLUMNS]
    conn.register("incoming_bars", ordered)
    try:
        conn.execute("INSERT OR REPLACE INTO saudi_stocks SELECT * FROM incoming_bars")
    finally:
        conn.unregister("incoming_bars")
    return len(ordered)


def ingest_market_data(
    conn: duckdb.DuckDBPyConnection,
    provider: MarketDataProvider,
    symbols: list[str],
    lookback: int = 200,
) -> int:
    """Fetch, clean, and upsert EOD bars. Returns the number of rows written."""
    raw = provider.fetch_eod(symbols, lookback)
    if raw.empty:
        return 0
    bars = clean_bars(raw)
    return upsert_bars(conn, bars)
