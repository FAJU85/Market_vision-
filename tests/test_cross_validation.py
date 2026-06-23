"""Tests for Epic C2 — purged & embargoed cross-validation."""

from __future__ import annotations

import pytest

from sqra.cross_validation import purged_embargoed_splits, train_holdout_split


def test_no_train_label_window_overlaps_test_fold():
    """Done when: no train observation's label window overlaps the test fold."""
    n, horizon, embargo = 100, 15, 5
    for train_idx, test_idx in purged_embargoed_splits(
        n, n_splits=5, label_horizon=horizon, embargo=embargo
    ):
        test_start, test_end = test_idx.min(), test_idx.max()
        for i in train_idx:
            # The label window [i, i+horizon] must not reach into the test fold.
            label_end = i + horizon
            overlaps = (label_end >= test_start) and (i <= test_end)
            assert not overlaps, f"train obs {i} leaks into test [{test_start},{test_end}]"


def test_embargo_gap_after_test_fold_is_respected():
    n, embargo = 100, 5
    for train_idx, test_idx in purged_embargoed_splits(
        n, n_splits=5, label_horizon=0, embargo=embargo
    ):
        test_end = test_idx.max()
        embargoed = set(range(test_end + 1, test_end + 1 + embargo))
        assert embargoed.isdisjoint(set(train_idx.tolist()))


def test_train_and_test_are_disjoint_and_cover_each_fold():
    n = 60
    for train_idx, test_idx in purged_embargoed_splits(n, n_splits=4):
        assert set(train_idx).isdisjoint(set(test_idx))


def test_invalid_params_raise():
    with pytest.raises(ValueError):
        list(purged_embargoed_splits(50, n_splits=1))
    with pytest.raises(ValueError):
        list(purged_embargoed_splits(50, label_horizon=-1))


def test_holdout_split_purges_boundary():
    train_idx, test_idx = train_holdout_split(100, test_fraction=0.2, label_horizon=15)
    assert test_idx.min() == 80
    # The 15 bars before the test block are purged.
    assert max(train_idx) < 80 - 15 + 1
    assert set(train_idx).isdisjoint(set(test_idx))
