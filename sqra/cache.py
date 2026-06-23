"""Nightly prediction cache and training cadence (Epic C4).

The post-market worker pre-computes model predictions and stores them in
``prediction_cache`` so the Gradio UI reads ready-made bounds on click instead
of running inference in the request path (NFR §7.1).

Training cadence (PRD §4.2):

* **Day core** — incremental fine-tune every run (restricted learning rate).
* **Swing core** — full hyperparameter sweep once per week on the sweep day.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import duckdb
import pandas as pd

from . import config
from .dashboard_data import DAY_MODE, SWING_MODE, day_bounds, swing_bounds
from .features import FEATURE_COLUMNS, build_features
from .models import load_model, predict, train_day_model, train_swing_model_sweep

# Tadawul's last trading day of the week is Thursday (weekday 3). The PRD names
# "Friday" for the weekly sweep, but the market is closed Fri/Sat; we run the
# sweep on the last trading day instead. Configurable for flexibility.
DEFAULT_SWEEP_WEEKDAY = 3


def should_full_sweep(day: date, sweep_weekday: int = DEFAULT_SWEEP_WEEKDAY) -> bool:
    """True if the weekly swing hyperparameter sweep should run on ``day``."""
    return day.weekday() == sweep_weekday


def _bounds_for(strategy_mode: str, recent: pd.DataFrame, model_path: Path) -> pd.DataFrame:
    booster = load_model(model_path)
    out = predict(booster, recent[FEATURE_COLUMNS])
    rows = recent[["symbol", "date", "close"]].copy()
    if strategy_mode == DAY_MODE:
        rows["pred_value"] = out
        rows["pred_upper"], rows["pred_lower"] = day_bounds(out)
    else:
        rows["pred_value"] = out
        rows["pred_upper"], rows["pred_lower"] = swing_bounds(recent["close"], out)
    rows["strategy_mode"] = strategy_mode
    rows["generated_at"] = datetime.now()
    return rows


def cache_predictions(
    conn: duckdb.DuckDBPyConnection,
    *,
    lookback: int = 60,
    day_model_path: Path | str | None = None,
    swing_model_path: Path | str | None = None,
) -> int:
    """Compute and upsert recent predictions for every symbol/mode.

    Returns the number of cache rows written.
    """
    day_path = Path(day_model_path) if day_model_path else config.DAY_MODEL_PATH
    swing_path = Path(swing_model_path) if swing_model_path else config.SWING_MODEL_PATH

    features = build_features(conn, drop_targets=True)
    if features.empty:
        return 0
    recent = features.groupby("symbol", group_keys=False).tail(lookback)

    frames = []
    if day_path.exists():
        frames.append(_bounds_for(DAY_MODE, recent, day_path))
    if swing_path.exists():
        frames.append(_bounds_for(SWING_MODE, recent, swing_path))
    if not frames:
        return 0

    cache_df = pd.concat(frames, ignore_index=True)[
        ["symbol", "date", "strategy_mode", "pred_value", "pred_upper",
         "pred_lower", "generated_at"]
    ]
    conn.register("incoming_predictions", cache_df)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO prediction_cache "
            "SELECT * FROM incoming_predictions"
        )
    finally:
        conn.unregister("incoming_predictions")
    return len(cache_df)


def run_training_cycle(
    conn: duckdb.DuckDBPyConnection,
    *,
    today: date | None = None,
    day_model_path: Path | str | None = None,
    swing_model_path: Path | str | None = None,
    sweep_weekday: int = DEFAULT_SWEEP_WEEKDAY,
) -> dict:
    """Run the nightly training + caching cadence. Returns a summary dict."""
    day = today or date.today()
    day_path = Path(day_model_path) if day_model_path else config.DAY_MODEL_PATH
    swing_path = Path(swing_model_path) if swing_model_path else config.SWING_MODEL_PATH

    features = build_features(conn)
    if features.empty:
        return {"trained_day": False, "swept_swing": False, "cached_rows": 0}

    # Day core: incremental fine-tune from the existing model when present.
    init = day_path if day_path.exists() else None
    train_day_model(features, model_path=day_path, init_model=init)

    swept = should_full_sweep(day, sweep_weekday)
    if swept or not swing_path.exists():
        train_swing_model_sweep(features, model_path=swing_path)

    cached = cache_predictions(
        conn, day_model_path=day_path, swing_model_path=swing_path
    )
    return {"trained_day": True, "swept_swing": swept, "cached_rows": cached}
