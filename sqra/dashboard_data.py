"""Read-only data assembly for the dashboard (Epic E2).

Pulls recent bars and overlays model predictions for a symbol. All access is
READ_ONLY (SRS §2.2); the UI never trains on a click (NFR §7.1) — it loads the
serialized cores and runs inference over pre-built features.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config
from .features import FEATURE_COLUMNS, build_features
from .models import load_model, predict

DAY_MODE = "Day Trading Core"
SWING_MODE = "Swing Trading Core"

# Fallback band when no model artifact exists yet.
FALLBACK_BAND = 0.02


def day_bounds(high_prediction, low_prediction):
    """Day-core bounds: the upper is the next-high model's output, the lower the
    next-low model's output (Core A predicts both bounds directly)."""
    return high_prediction, low_prediction


def swing_bounds(close, probability):
    """Upper/lower bounds from the swing core's up-probability."""
    return close * (1 + probability * 0.05), close * (1 - probability * 0.03)


def predicted_bounds(
    conn,
    symbol: str,
    strategy_mode: str,
    *,
    lookback: int = 60,
    day_model_path: Path | str | None = None,
    day_low_model_path: Path | str | None = None,
    swing_model_path: Path | str | None = None,
) -> pd.DataFrame:
    """Return recent bars for ``symbol`` with predicted upper/lower bounds.

    Falls back to a fixed ±2% band if the model artifact is missing, so the UI
    still renders before the first training run.
    """
    features = build_features(conn, symbols=[symbol], drop_targets=True)
    if features.empty:
        return pd.DataFrame()
    recent = features.tail(lookback).copy()

    day_path = Path(day_model_path) if day_model_path else config.DAY_MODEL_PATH
    day_low_path = Path(day_low_model_path) if day_low_model_path else config.DAY_LOW_MODEL_PATH
    swing_path = Path(swing_model_path) if swing_model_path else config.SWING_MODEL_PATH

    try:
        if strategy_mode == DAY_MODE:
            high_pred = predict(load_model(day_path), recent[FEATURE_COLUMNS])
            low_pred = predict(load_model(day_low_path), recent[FEATURE_COLUMNS])
            recent["pred_upper"], recent["pred_lower"] = day_bounds(high_pred, low_pred)
        else:
            booster = load_model(swing_path)
            prob = predict(booster, recent[FEATURE_COLUMNS])
            recent["pred_upper"], recent["pred_lower"] = swing_bounds(recent["close"], prob)
    except Exception:  # noqa: BLE001 - the UI must render even before first training
        recent["pred_upper"] = recent["close"] * (1 + FALLBACK_BAND)
        recent["pred_lower"] = recent["close"] * (1 - FALLBACK_BAND)

    return recent


def cached_bounds(conn, symbol: str, strategy_mode: str):
    """Read pre-computed bounds for a symbol/mode from the prediction cache.

    Returns a DataFrame (date, close, pred_upper, pred_lower) joined against the
    price store, or an empty frame if the cache has no rows (C4: UI reads the
    cache rather than running inference on a click).
    """
    return conn.execute(
        """
        SELECT p.date, s.close, p.pred_upper, p.pred_lower
        FROM prediction_cache p
        JOIN saudi_stocks s ON s.symbol = p.symbol AND s.date = p.date
        WHERE p.symbol = ? AND p.strategy_mode = ?
        ORDER BY p.date
        """,
        [symbol, strategy_mode],
    ).df()


def available_symbols(conn) -> list[str]:
    """Distinct symbols present in the store, sorted."""
    rows = conn.execute(
        "SELECT DISTINCT symbol FROM saudi_stocks ORDER BY symbol"
    ).fetchall()
    return [r[0] for r in rows]
