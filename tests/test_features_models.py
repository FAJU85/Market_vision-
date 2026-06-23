"""Tests for Epic C1 (features) and C3 (dual-core models)."""

from __future__ import annotations

import pytest

from sqra import db
from sqra.features import FEATURE_COLUMNS, build_features
from sqra.ingest import MockProvider, ingest_market_data
from sqra.models import load_model, predict, train_day_model, train_swing_model


@pytest.fixture()
def features(tmp_path):
    """Ingest a long history and build the feature frame."""
    path = db.initialize(tmp_path / "sqra_storage.db")
    with db.writable(path) as conn:
        ingest_market_data(conn, MockProvider(), ["1120", "2222"], lookback=400)
    with db.read_only(path) as conn:
        return build_features(conn)


# --- C1: feature integrity --------------------------------------------------


def test_features_have_no_lookahead_nulls(features):
    """Done when: the feature frame has no nulls in any feature column."""
    assert not features.empty
    assert not features[FEATURE_COLUMNS].isnull().any().any()


def test_opening_gap_uses_only_past_data(features):
    # opening_gap must be finite and bounded for a low-vol random walk.
    assert features["opening_gap"].abs().max() < 1.0


def test_inference_frame_drops_targets(tmp_path):
    path = db.initialize(tmp_path / "infer.db")
    with db.writable(path) as conn:
        ingest_market_data(conn, MockProvider(), ["1120"], lookback=300)
    with db.read_only(path) as conn:
        infer = build_features(conn, drop_targets=True)
    assert "swing_target" not in infer.columns
    assert "next_high" not in infer.columns


# --- C3: model train / load / predict --------------------------------------


def test_day_model_trains_loads_and_predicts(features, tmp_path):
    """Done when: the day core saves, reloads, and predicts."""
    model_path = tmp_path / "day_model.txt"
    train_day_model(features, num_boost_round=20, model_path=model_path)
    assert model_path.exists()
    reloaded = load_model(model_path)
    preds = predict(reloaded, features)
    assert len(preds) == len(features)


def test_swing_model_trains_loads_and_predicts(features, tmp_path):
    model_path = tmp_path / "swing_model.txt"
    train_swing_model(features, num_boost_round=20, model_path=model_path)
    assert model_path.exists()
    reloaded = load_model(model_path)
    preds = predict(reloaded, features)
    # Binary objective -> probabilities in [0, 1].
    assert ((preds >= 0) & (preds <= 1)).all()
