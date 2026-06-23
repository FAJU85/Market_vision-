"""Live market-data provider (deferred backlog #1).

A real :class:`MarketDataProvider` (see ``sqra/ingest.py``) that fetches adjusted
EOD bars for Tadawul equities plus the TASI index and Brent crude macro node.

Network access is isolated behind an injectable ``downloader`` callable, so unit
tests mock it and never touch the network. The default downloader uses
``yfinance``. Any provider credentials are read from ``HF_SECRET_*`` env vars.
Failures retry, then fall back gracefully (skip the failing ticker / return what
succeeded) so the cron never crashes — ``MockProvider`` remains the offline
default.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable

import pandas as pd

from .config import get_secret
from .ingest import BAR_COLUMNS

# Yahoo Finance tickers for the macro nodes.
TASI_TICKER = "^TASI"
BRENT_TICKER = "BZ=F"

# A downloader returns a DataFrame indexed by date with at least the columns
# Open, High, Low, Close, Adj Close, Volume (the yfinance layout).
Downloader = Callable[[str, int], pd.DataFrame]


def map_symbol(tadawul_symbol: str) -> str:
    """Map a Tadawul numeric ticker to Yahoo's format (``1120`` -> ``1120.SR``)."""
    s = str(tadawul_symbol).strip()
    if s.startswith("^") or "." in s or "=" in s:
        return s  # already an index / fully-qualified / futures ticker
    return f"{s}.SR"


def _yfinance_downloader(ticker: str, lookback: int) -> pd.DataFrame:
    """Default downloader backed by yfinance (imported lazily)."""
    import yfinance as yf

    # Add headroom so non-trading days still yield ``lookback`` bars.
    period_days = max(lookback * 2, lookback + 15)
    df = yf.download(
        ticker,
        period=f"{period_days}d",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df


def _with_retry(fn: Callable[[], pd.DataFrame | None], attempts: int = 3) -> pd.DataFrame | None:
    """Run ``fn`` with simple exponential backoff; return None on total failure."""
    delay = 1.0
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - provider must not crash the cron
            print(f"[live-provider] attempt {attempt}/{attempts} failed: {exc}", file=sys.stderr)
            if attempt < attempts:
                time.sleep(delay)
                delay *= 2
    return None


def _close_series(df: pd.DataFrame | None) -> pd.Series:
    """Extract a date->close Series from a downloaded frame (empty if missing)."""
    if df is None or df.empty or "Close" not in df.columns:
        return pd.Series(dtype="float64")
    series = df["Close"].copy()
    series.index = pd.to_datetime(series.index).date
    return series


class YahooProvider:
    """Fetches live EOD bars for Tadawul equities + TASI + Brent macro columns."""

    def __init__(self, downloader: Downloader | None = None, *, attempts: int = 3) -> None:
        self._download = downloader or _yfinance_downloader
        self._attempts = attempts
        # Read an optional provider API key (unused by yfinance, but supported
        # for paid providers); never logged.
        self._api_key = get_secret("MARKET_API_KEY")

    def _fetch(self, ticker: str, lookback: int) -> pd.DataFrame | None:
        return _with_retry(lambda: self._download(ticker, lookback), self._attempts)

    def fetch_eod(self, symbols: list[str], lookback: int = 200) -> pd.DataFrame:
        tasi = _close_series(self._fetch(TASI_TICKER, lookback))
        brent = _close_series(self._fetch(BRENT_TICKER, lookback))

        records: list[pd.DataFrame] = []
        for symbol in symbols:
            raw = self._fetch(map_symbol(symbol), lookback)
            if raw is None or raw.empty:
                continue  # skip the failing ticker, keep going
            frame = self._normalize(symbol, raw, tasi, brent)
            if not frame.empty:
                records.append(frame)

        if not records:
            return pd.DataFrame(columns=BAR_COLUMNS)
        return pd.concat(records, ignore_index=True)[BAR_COLUMNS]

    @staticmethod
    def _normalize(
        symbol: str, raw: pd.DataFrame, tasi: pd.Series, brent: pd.Series
    ) -> pd.DataFrame:
        df = raw.copy()
        dates = pd.to_datetime(df.index).date
        adj = df["Adj Close"] if "Adj Close" in df.columns else df["Close"]
        out = pd.DataFrame(
            {
                "symbol": symbol,
                "date": dates,
                "open": df["Open"].to_numpy(),
                "high": df["High"].to_numpy(),
                "low": df["Low"].to_numpy(),
                "close": df["Close"].to_numpy(),
                "adj_close": adj.to_numpy(),
                "volume": df["Volume"].fillna(0).astype("int64").to_numpy(),
            }
        )
        # Merge macro nodes by date, forward/back-filling small gaps.
        out["tasi_close"] = out["date"].map(tasi).ffill().bfill()
        out["brent_price"] = out["date"].map(brent).ffill().bfill()
        return out.dropna(subset=["open", "high", "low", "close"])
