"""Tests for Epic C4 — training cadence and prediction cache."""

from __future__ import annotations

from datetime import date

import pytest

from sqra import db
from sqra.cache import (
    DEFAULT_SWEEP_WEEKDAY,
    cache_predictions,
    run_training_cycle,
    should_full_sweep,
)
from sqra.dashboard_data import DAY_MODE, cached_bounds
from sqra.ingest import MockProvider, ingest_market_data


@pytest.fixture()
def trained_db(tmp_path):
    """A DB with enough history that build_features yields trainable rows."""
    path = db.initialize(tmp_path / "c4.db")
    with db.writable(path) as conn:
        ingest_market_data(conn, MockProvider(), ["1120", "2222"], lookback=400)
    return path


# --- cadence ---------------------------------------------------------------


def test_should_full_sweep_on_sweep_day():
    # 2024-01-04 is a Thursday (weekday 3).
    assert should_full_sweep(date(2024, 1, 4), sweep_weekday=DEFAULT_SWEEP_WEEKDAY)


def test_should_not_full_sweep_other_days():
    assert not should_full_sweep(date(2024, 1, 7))  # Sunday


# --- training cycle + cache ------------------------------------------------


def test_training_cycle_populates_cache(trained_db):
    """Done when: the cache table is populated after a training cycle."""
    with db.writable(trained_db) as conn:
        summary = run_training_cycle(
            conn,
            today=date(2024, 1, 4),  # sweep day -> swing trained too
            day_model_path=trained_db.parent / "day.txt",
            day_low_model_path=trained_db.parent / "day_low.txt",
            swing_model_path=trained_db.parent / "swing.txt",
        )
        assert summary["trained_day"] is True
        assert summary["swept_swing"] is True
        assert summary["cached_rows"] > 0
        count = conn.execute("SELECT COUNT(*) FROM prediction_cache").fetchone()[0]
    assert count > 0


def test_ui_reads_cached_bounds(trained_db):
    """Done when: the UI reads pre-computed predictions from the cache."""
    with db.writable(trained_db) as conn:
        run_training_cycle(
            conn,
            today=date(2024, 1, 4),
            day_model_path=trained_db.parent / "day.txt",
            day_low_model_path=trained_db.parent / "day_low.txt",
            swing_model_path=trained_db.parent / "swing.txt",
        )
    with db.read_only(trained_db) as conn:
        df = cached_bounds(conn, "1120", DAY_MODE)
    assert not df.empty
    assert {"date", "close", "pred_upper", "pred_lower"} <= set(df.columns)


def test_cache_predictions_noop_without_models(trained_db):
    with db.writable(trained_db) as conn:
        written = cache_predictions(
            conn,
            day_model_path=trained_db.parent / "absent_day.txt",
            day_low_model_path=trained_db.parent / "absent_day_low.txt",
            swing_model_path=trained_db.parent / "absent_swing.txt",
        )
    assert written == 0
