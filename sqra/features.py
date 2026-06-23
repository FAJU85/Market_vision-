"""Feature engineering in DuckDB SQL (Epic C1).

All transforms run as vectorized window functions inside DuckDB and only ever
reference current or past bars, so feature columns carry no look-ahead bias
(PRD §4.2, SRS §3.2). Forward-looking *targets* (next-day high/low, 15-day swing
return) are produced for training and dropped before inference.

Window functions partition by ``symbol`` so rolling windows never span two
instruments.
"""

from __future__ import annotations

import duckdb
import pandas as pd

# Inputs to the models. ``sma_crossover`` is the 50/200-day trend signal.
FEATURE_COLUMNS = [
    "opening_gap",
    "stoch_5d",
    "ma_50",
    "ma_200",
    "sma_crossover",
    "tasi_close",
    "brent_price",
]

# Forward-looking labels (never fed as features).
TARGET_COLUMNS = ["next_high", "next_low", "swing_target"]

SWING_HORIZON = 15

_FEATURE_SQL = f"""
WITH base AS (
    SELECT
        symbol, date, open, high, low, close, adj_close, volume,
        tasi_close, brent_price,
        LAG(close, 1) OVER w AS prev_close,
        MIN(low)  OVER w5 AS roll_low_5,
        MAX(high) OVER w5 AS roll_high_5,
        AVG(close) OVER w50  AS ma_50,
        AVG(close) OVER w200 AS ma_200,
        LEAD(high, 1) OVER w AS next_high,
        LEAD(low, 1)  OVER w AS next_low,
        LEAD(close, {SWING_HORIZON}) OVER w AS future_close,
        COUNT(*) OVER w200 AS bars_seen
    FROM saudi_stocks
    WINDOW
        w   AS (PARTITION BY symbol ORDER BY date),
        w5  AS (PARTITION BY symbol ORDER BY date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW),
        w50 AS (PARTITION BY symbol ORDER BY date ROWS BETWEEN 49 PRECEDING AND CURRENT ROW),
        w200 AS (PARTITION BY symbol ORDER BY date ROWS BETWEEN 199 PRECEDING AND CURRENT ROW)
)
SELECT
    symbol, date, close,
    (open - prev_close) / NULLIF(prev_close, 0) AS opening_gap,
    (close - roll_low_5) / NULLIF(roll_high_5 - roll_low_5, 0) AS stoch_5d,
    ma_50,
    ma_200,
    ma_50 - ma_200 AS sma_crossover,
    tasi_close,
    brent_price,
    next_high,
    next_low,
    (future_close - close) / NULLIF(close, 0) AS swing_target
FROM base
WHERE bars_seen >= 200            -- full 200-day MA window only
ORDER BY symbol, date
"""


def build_features(
    conn: duckdb.DuckDBPyConnection,
    symbols: list[str] | None = None,
    *,
    drop_targets: bool = False,
) -> pd.DataFrame:
    """Return a feature/target frame with no look-ahead nulls in the features.

    Rows without a full 200-day history are excluded. When ``drop_targets`` is
    True (inference), rows are kept even if forward targets are null; otherwise
    (training) rows with any null target are dropped.
    """
    frame = conn.execute(_FEATURE_SQL).df()
    if symbols is not None:
        frame = frame[frame["symbol"].isin(symbols)]

    frame = frame.dropna(subset=FEATURE_COLUMNS)
    if not drop_targets:
        frame = frame.dropna(subset=TARGET_COLUMNS)
    else:
        frame = frame.drop(columns=TARGET_COLUMNS, errors="ignore")
    return frame.reset_index(drop=True)
