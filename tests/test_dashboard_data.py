"""Tests for Epic E2 — dashboard data assembly."""

from __future__ import annotations

import pytest

from sqra import db
from sqra.dashboard_data import DAY_MODE, available_symbols, predicted_bounds
from sqra.features import build_features
from sqra.ingest import MockProvider, ingest_market_data
from sqra.models import train_day_model


@pytest.fixture()
def populated_db(tmp_path):
    path = db.initialize(tmp_path / "dash.db")
    with db.writable(path) as conn:
        ingest_market_data(conn, MockProvider(), ["1120", "2222"], lookback=300)
    return path


def test_available_symbols(populated_db):
    with db.read_only(populated_db) as conn:
        assert available_symbols(conn) == ["1120", "2222"]


def test_predicted_bounds_fallback_band_without_model(populated_db):
    """Before any training, bounds fall back to a fixed +/-2% band (no crash)."""
    with db.read_only(populated_db) as conn:
        df = predicted_bounds(conn, "1120", DAY_MODE, day_model_path="/nonexistent.txt")
    assert not df.empty
    assert (df["pred_upper"] > df["close"]).all()
    assert (df["pred_lower"] < df["close"]).all()


def test_predicted_bounds_uses_trained_model(populated_db, tmp_path):
    model_path = tmp_path / "day_model.txt"
    with db.read_only(populated_db) as conn:
        features = build_features(conn, symbols=["1120"])
    train_day_model(features, num_boost_round=20, model_path=model_path)

    with db.read_only(populated_db) as conn:
        df = predicted_bounds(conn, "1120", DAY_MODE, day_model_path=model_path)
    assert not df.empty
    assert {"pred_upper", "pred_lower"} <= set(df.columns)
