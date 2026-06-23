"""Outlier defense for ingested EOD bars (Epic B3).

Implements the modified Z-score guardrail from PRD §4.1 / SRS §3.1.3:

* Compute a rolling 5-day median and median absolute deviation (MAD) of close.
* Modified Z-score:  M = 0.6745 * (close - median) / MAD.
* A bar is an *illiquid anomaly* when ``|M| > 4.5`` **and** its volume is more
  than ``volume_sigma`` (default 2) standard deviations below the 20-day median
  volume.
* For each anomaly: override close/adj_close with the previous day's close, set
  the training ``sample_weight`` to 0, and emit an alert to stderr.

All functions are pure (operate on a per-symbol DataFrame), so they unit-test
without any database or network I/O.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

MAD_SCALE = 0.6745
Z_THRESHOLD = 4.5
PRICE_WINDOW = 5
VOLUME_WINDOW = 20
VOLUME_SIGMA = 2.0
# Guards against division by zero when a flat window has MAD == 0.
_MAD_FLOOR = 1e-9


def _rolling_modified_zscore(close: pd.Series, window: int = PRICE_WINDOW) -> pd.Series:
    """Modified Z-score of each value against its trailing ``window`` median."""
    median = close.rolling(window, min_periods=window).median()
    mad = (close - median).abs().rolling(window, min_periods=window).median()
    mad = mad.fillna(0.0).clip(lower=_MAD_FLOOR)
    return MAD_SCALE * (close - median) / mad


def detect_anomalies(df: pd.DataFrame, volume_sigma: float = VOLUME_SIGMA) -> pd.Series:
    """Return a boolean Series flagging illiquid-anomaly bars for one symbol.

    ``df`` must be sorted by date and contain ``close`` and ``volume`` columns.
    """
    mod_z = _rolling_modified_zscore(df["close"])

    vol_median = df["volume"].rolling(VOLUME_WINDOW, min_periods=1).median()
    vol_std = df["volume"].rolling(VOLUME_WINDOW, min_periods=1).std().fillna(0.0)
    low_volume = df["volume"] < (vol_median - volume_sigma * vol_std)

    return (mod_z.abs() > Z_THRESHOLD) & low_volume


def apply_outlier_defense(
    df: pd.DataFrame, *, symbol: str | None = None, volume_sigma: float = VOLUME_SIGMA
) -> pd.DataFrame:
    """Return a copy of ``df`` with anomalies smoothed and sample weights set.

    Adds an ``is_outlier`` flag and a ``sample_weight`` column (0.0 for anomalies,
    1.0 otherwise). Anomalous close/adj_close are overridden with the prior bar's
    close. An alert is logged to stderr for each anomaly.
    """
    out = df.sort_values("date").reset_index(drop=True).copy()
    out["is_outlier"] = detect_anomalies(out, volume_sigma=volume_sigma)
    out["sample_weight"] = np.where(out["is_outlier"], 0.0, 1.0)

    prev_close = out["close"].shift(1)
    for idx in out.index[out["is_outlier"]]:
        if idx == 0 or pd.isna(prev_close.iloc[idx]):
            # No prior bar to fall back to; keep the value but flag it.
            continue
        replacement = prev_close.iloc[idx]
        out.loc[idx, "close"] = replacement
        if "adj_close" in out.columns:
            out.loc[idx, "adj_close"] = replacement
        tag = f"{symbol} " if symbol else ""
        print(
            f"[outlier-defense] {tag}illiquid anomaly on {out.loc[idx, 'date']}: "
            f"close overridden with previous close {replacement:.4f}",
            file=sys.stderr,
        )
    return out
