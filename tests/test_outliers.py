"""Tests for Epic B3 — outlier defense."""

from __future__ import annotations

import numpy as np
import pandas as pd

from sqra.outliers import apply_outlier_defense, detect_anomalies


def _stable_series(n: int = 40, price: float = 100.0, volume: int = 1_000_000):
    dates = pd.date_range("2024-01-01", periods=n, freq="B")
    rng = np.random.default_rng(0)
    close = price + rng.normal(0, 0.05, n)  # very low volatility
    return pd.DataFrame(
        {
            "symbol": "TEST",
            "date": [d.date() for d in dates],
            "close": close,
            "adj_close": close,
            "volume": volume,
        }
    )


def test_synthetic_spike_with_low_volume_is_flagged_and_overridden():
    """Done when: a synthetic spike on low volume is overridden + weight zeroed."""
    df = _stable_series()
    spike_idx = 30
    prev_close = df.loc[spike_idx - 1, "close"]
    df.loc[spike_idx, "close"] = 100.0 * 1.5  # +50% spike
    df.loc[spike_idx, "adj_close"] = 100.0 * 1.5
    df.loc[spike_idx, "volume"] = 1  # illiquid

    result = apply_outlier_defense(df, symbol="TEST")

    assert bool(result.loc[spike_idx, "is_outlier"]) is True
    assert result.loc[spike_idx, "sample_weight"] == 0.0
    # Price overridden with the previous bar's close.
    assert result.loc[spike_idx, "close"] == prev_close
    assert result.loc[spike_idx, "adj_close"] == prev_close


def test_spike_on_normal_volume_is_not_flagged():
    """A price move on healthy volume is a real move, not an illiquid anomaly."""
    df = _stable_series()
    df.loc[30, "close"] = 100.0 * 1.5
    df.loc[30, "volume"] = 5_000_000  # high volume -> legitimate
    result = apply_outlier_defense(df, symbol="TEST")
    assert bool(result.loc[30, "is_outlier"]) is False


def test_clean_series_has_no_anomalies_and_full_weight():
    df = _stable_series()
    result = apply_outlier_defense(df, symbol="TEST")
    assert not detect_anomalies(df).any()
    assert (result["sample_weight"] == 1.0).all()
