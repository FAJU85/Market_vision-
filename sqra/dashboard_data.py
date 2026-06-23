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


def predicted_bounds(
    conn,
    symbol: str,
    strategy_mode: str,
    *,
    lookback: int = 60,
    day_model_path: Path | str | None = None,
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
    swing_path = Path(swing_model_path) if swing_model_path else config.SWING_MODEL_PATH

    try:
        if strategy_mode == DAY_MODE:
            booster = load_model(day_path)
            pred = predict(booster, recent[FEATURE_COLUMNS])
            recent["pred_upper"] = pred * 1.01
            recent["pred_lower"] = pred * 0.99
        else:
            booster = load_model(swing_path)
            prob = predict(booster, recent[FEATURE_COLUMNS])
            recent["pred_upper"] = recent["close"] * (1 + prob * 0.05)
            recent["pred_lower"] = recent["close"] * (1 - prob * 0.03)
    except Exception:  # noqa: BLE001 - the UI must render even before first training
        recent["pred_upper"] = recent["close"] * 1.02
        recent["pred_lower"] = recent["close"] * 0.98

    return recent


def available_symbols(conn) -> list[str]:
    """Distinct symbols present in the store, sorted."""
    rows = conn.execute(
        "SELECT DISTINCT symbol FROM saudi_stocks ORDER BY symbol"
    ).fetchall()
    return [r[0] for r in rows]
