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


def train_day_model(
    features: pd.DataFrame,
    *,
    num_boost_round: int = 100,
    model_path: Path | str | None = None,
) -> lgb.Booster:
    """Train Core A (next-day high bound) and serialize it."""
    train_df, _ = _split(features)
    weight = train_df["sample_weight"] if "sample_weight" in train_df else None
    dataset = lgb.Dataset(train_df[FEATURE_COLUMNS], label=train_df["next_high"], weight=weight)
    booster = lgb.train(_DAY_PARAMS, dataset, num_boost_round=num_boost_round)
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


def load_model(model_path: Path | str) -> lgb.Booster:
    """Load a serialized LightGBM core."""
    return lgb.Booster(model_file=str(model_path))


def predict(booster: lgb.Booster, features: pd.DataFrame) -> np.ndarray:
    """Run inference over the canonical feature columns."""
    return booster.predict(features[FEATURE_COLUMNS])
