"""Dual-core LightGBM engine (Epic C3).

* **Core A — Day Trading:** regression predicting the next-day high bound
  (MSE). Serialized to ``day_model.txt``.
* **Core B — Swing Trading:** binary classifier for a positive 15-day forward
  return beyond the friction threshold (log-loss). Serialized to
  ``swing_model.txt``.

Both cores train on the purged+embargoed holdout split so evaluation never sees
leaked future information (PRD §4.2). ``sample_weight`` from the outlier defense
(Epic B3) is honored when supplied.
"""

from __future__ import annotations

from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from . import config
from .cross_validation import train_holdout_split
from .features import FEATURE_COLUMNS, SWING_HORIZON

# Swing label: a move beyond round-trip friction (0.51%) is "actionable up".
SWING_UP_THRESHOLD = 0.02

_DAY_PARAMS = {
    "objective": "regression",
    "metric": "rmse",
    "learning_rate": 0.05,
    "num_leaves": 15,
    "verbose": -1,
}
_SWING_PARAMS = {
    "objective": "binary",
    "metric": "binary_logloss",
    "learning_rate": 0.05,
    "num_leaves": 15,
    "verbose": -1,
}


def _split(features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_idx, test_idx = train_holdout_split(
        len(features), test_fraction=0.2, label_horizon=SWING_HORIZON, embargo=5
    )
    return features.iloc[train_idx], features.iloc[test_idx]


# Restricted learning rate for nightly incremental fine-tuning (PRD §4.2).
INCREMENTAL_LEARNING_RATE = 1e-5


def train_day_model(
    features: pd.DataFrame,
    *,
    num_boost_round: int = 100,
    model_path: Path | str | None = None,
    init_model: lgb.Booster | Path | str | None = None,
    learning_rate: float | None = None,
) -> lgb.Booster:
    """Train Core A (next-day high bound) and serialize it.

    When ``init_model`` is supplied, boosting continues from that model — the
    nightly incremental fine-tune — typically with a restricted
    ``learning_rate`` (default ``1e-5`` in that mode).
    """
    train_df, _ = _split(features)
    weight = train_df["sample_weight"] if "sample_weight" in train_df else None
    dataset = lgb.Dataset(train_df[FEATURE_COLUMNS], label=train_df["next_high"], weight=weight)

    params = dict(_DAY_PARAMS)
    if learning_rate is not None:
        params["learning_rate"] = learning_rate
    elif init_model is not None:
        params["learning_rate"] = INCREMENTAL_LEARNING_RATE

    init = load_model(init_model) if isinstance(init_model, (str, Path)) else init_model
    booster = lgb.train(params, dataset, num_boost_round=num_boost_round, init_model=init)
    path = Path(model_path) if model_path is not None else config.DAY_MODEL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(path))
    return booster


def train_swing_model(
    features: pd.DataFrame,
    *,
    num_boost_round: int = 150,
    model_path: Path | str | None = None,
) -> lgb.Booster:
    """Train Core B (15-day directional classifier) and serialize it."""
    train_df, _ = _split(features)
    label = (train_df["swing_target"] > SWING_UP_THRESHOLD).astype(int)
    weight = train_df["sample_weight"] if "sample_weight" in train_df else None
    dataset = lgb.Dataset(train_df[FEATURE_COLUMNS], label=label, weight=weight)
    booster = lgb.train(_SWING_PARAMS, dataset, num_boost_round=num_boost_round)
    path = Path(model_path) if model_path is not None else config.SWING_MODEL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(path))
    return booster


# Small grid for the weekly swing hyperparameter sweep (PRD §4.2).
_SWING_SWEEP_GRID = [
    {"num_leaves": 15, "learning_rate": 0.05},
    {"num_leaves": 31, "learning_rate": 0.05},
    {"num_leaves": 15, "learning_rate": 0.1},
]


def train_swing_model_sweep(
    features: pd.DataFrame,
    *,
    num_boost_round: int = 150,
    model_path: Path | str | None = None,
    grid: list[dict] | None = None,
) -> lgb.Booster:
    """Full hyperparameter sweep for Core B; keep the lowest-logloss model.

    Evaluates each grid point on the purged+embargoed holdout test fold and
    serializes the best booster (PRD §4.2 — weekly Friday sweep).
    """
    train_df, test_df = _split(features)
    y_train = (train_df["swing_target"] > SWING_UP_THRESHOLD).astype(int)
    y_test = (test_df["swing_target"] > SWING_UP_THRESHOLD).astype(int)
    weight = train_df["sample_weight"] if "sample_weight" in train_df else None
    train_set = lgb.Dataset(train_df[FEATURE_COLUMNS], label=y_train, weight=weight)

    best_booster, best_loss = None, float("inf")
    for overrides in (grid or _SWING_SWEEP_GRID):
        params = {**_SWING_PARAMS, **overrides}
        booster = lgb.train(params, train_set, num_boost_round=num_boost_round)
        probs = booster.predict(test_df[FEATURE_COLUMNS])
        loss = _binary_logloss(y_test.to_numpy(), probs)
        if loss < best_loss:
            best_booster, best_loss = booster, loss

    path = Path(model_path) if model_path is not None else config.SWING_MODEL_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    best_booster.save_model(str(path))
    return best_booster


def _binary_logloss(y_true: np.ndarray, probs: np.ndarray, eps: float = 1e-15) -> float:
    p = np.clip(probs, eps, 1 - eps)
    return float(-np.mean(y_true * np.log(p) + (1 - y_true) * np.log(1 - p)))


def load_model(model_path: Path | str) -> lgb.Booster:
    """Load a serialized LightGBM core."""
    return lgb.Booster(model_file=str(model_path))


def predict(booster: lgb.Booster, features: pd.DataFrame) -> np.ndarray:
    """Run inference over the canonical feature columns."""
    return booster.predict(features[FEATURE_COLUMNS])
