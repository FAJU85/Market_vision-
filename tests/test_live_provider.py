"""Tests for the live market-data provider (backlog #1). No real network."""

from __future__ import annotations

import pandas as pd
import pytest

from sqra.ingest import BAR_COLUMNS
from sqra.live_provider import (
    BRENT_TICKER,
    TASI_TICKER,
    YahooProvider,
    map_symbol,
)

# --- US-1: symbol mapping --------------------------------------------------


@pytest.mark.parametrize(
    "raw,mapped",
    [
        ("1120", "1120.SR"),
        (2222, "2222.SR"),
        (TASI_TICKER, TASI_TICKER),     # index passes through
        (BRENT_TICKER, BRENT_TICKER),   # futures ticker passes through
        ("AAPL.US", "AAPL.US"),         # already qualified
    ],
)
def test_map_symbol(raw, mapped):
    assert map_symbol(raw) == mapped


# --- US-2: fetch contract with a mocked downloader -------------------------


def _yahoo_frame(base: float):
    idx = pd.date_range("2024-01-01", periods=5, freq="B")
    return pd.DataFrame(
        {
            "Open": base, "High": base * 1.01, "Low": base * 0.99,
            "Close": base, "Adj Close": base, "Volume": 1000,
        },
        index=idx,
    )


def _fake_downloader(ticker: str, lookback: int) -> pd.DataFrame:
    if ticker == TASI_TICKER:
        return _yahoo_frame(12000.0)
    if ticker == BRENT_TICKER:
        return _yahoo_frame(82.5)
    return _yahoo_frame(50.0)


def test_fetch_eod_returns_canonical_columns_with_macro_merge():
    provider = YahooProvider(downloader=_fake_downloader)
    df = provider.fetch_eod(["1120", "2222"], lookback=5)

    assert list(df.columns) == BAR_COLUMNS
    assert set(df["symbol"]) == {"1120", "2222"}
    # Macro columns merged by date from the index/Brent series.
    assert (df["tasi_close"] == 12000.0).all()
    assert (df["brent_price"] == 82.5).all()
    assert len(df) == 2 * 5


def test_failing_ticker_is_skipped_not_crashed():
    def flaky(ticker: str, lookback: int):
        if ticker == "2222.SR":
            raise ConnectionError("boom")
        return _fake_downloader(ticker, lookback)

    provider = YahooProvider(downloader=flaky, attempts=2)
    df = provider.fetch_eod(["1120", "2222"], lookback=5)
    # 1120 still ingested; 2222 skipped after retries; no exception raised.
    assert set(df["symbol"]) == {"1120"}


def test_total_failure_returns_empty_frame():
    def always_fail(ticker: str, lookback: int):
        raise TimeoutError("network down")

    provider = YahooProvider(downloader=always_fail, attempts=2)
    df = provider.fetch_eod(["1120"], lookback=5)
    assert df.empty
    assert list(df.columns) == BAR_COLUMNS


def test_provider_output_flows_through_ingestion(tmp_path):
    """The live provider plugs into the existing ingestion pipeline unchanged."""
    from sqra import db
    from sqra.ingest import ingest_market_data

    path = db.initialize(tmp_path / "live.db")
    provider = YahooProvider(downloader=_fake_downloader)
    with db.writable(path) as conn:
        written = ingest_market_data(conn, provider, ["1120"], lookback=5)
    assert written == 5
