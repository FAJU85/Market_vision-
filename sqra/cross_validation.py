"""Purged & Embargoed time-series cross-validation (Epic C2).

Standard K-Fold leaks information in financial time series because a label spans
a forward horizon (e.g. the 15-day swing target uses prices up to ``t + 15``).
Following de Prado, we:

* **Purge** training observations whose label-evaluation window
  ``[i, i + label_horizon]`` overlaps the test fold's index range.
* **Embargo** a fixed number of bars immediately *after* the test fold so the
  test set's own forward labels cannot leak into subsequent training via
  autoregressive memory.

Splits operate on integer positions of a date-sorted index, so the logic is
pure and unit-testable without any model or data dependency (PRD §4.2, SRS §3.2.3).
"""

from __future__ import annotations

from collections.abc import Iterator

import numpy as np


def purged_embargoed_splits(
    n_samples: int,
    *,
    n_splits: int = 5,
    label_horizon: int = 15,
    embargo: int = 5,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield ``(train_idx, test_idx)`` arrays for each contiguous test fold.

    Indices refer to positions in a chronologically sorted dataset.
    """
    if n_samples <= 0:
        return
    if n_splits < 2:
        raise ValueError("n_splits must be >= 2")
    if label_horizon < 0 or embargo < 0:
        raise ValueError("label_horizon and embargo must be non-negative")

    indices = np.arange(n_samples)
    fold_edges = np.linspace(0, n_samples, n_splits + 1, dtype=int)

    for k in range(n_splits):
        test_start, test_end = int(fold_edges[k]), int(fold_edges[k + 1])
        if test_start >= test_end:
            continue
        test_idx = indices[test_start:test_end]

        train_mask = np.ones(n_samples, dtype=bool)
        train_mask[test_start:test_end] = False

        # Purge: drop any train obs whose label window [i, i+label_horizon]
        # overlaps the test fold's index range [test_start, test_end).
        purge_lo = max(0, test_start - label_horizon)
        train_mask[purge_lo:test_start] = False

        # Embargo: drop train obs in [test_end, test_end + embargo).
        embargo_hi = min(n_samples, test_end + embargo)
        train_mask[test_end:embargo_hi] = False

        train_idx = indices[train_mask]
        yield train_idx, test_idx


def train_holdout_split(
    n_samples: int,
    *,
    test_fraction: float = 0.2,
    label_horizon: int = 15,
    embargo: int = 5,
) -> tuple[np.ndarray, np.ndarray]:
    """Return a single purged+embargoed (train, test) split for a final holdout.

    The test block is the most recent ``test_fraction`` of the data; training is
    everything before it minus the purge window. (With a trailing holdout there
    are no post-test bars to embargo, but the parameter is kept for symmetry.)
    """
    if not 0.0 < test_fraction < 1.0:
        raise ValueError("test_fraction must be in (0, 1)")
    test_start = int(n_samples * (1 - test_fraction))
    indices = np.arange(n_samples)
    test_idx = indices[test_start:]

    train_mask = np.ones(n_samples, dtype=bool)
    train_mask[test_start:] = False
    purge_lo = max(0, test_start - label_horizon)
    train_mask[purge_lo:test_start] = False
    return indices[train_mask], test_idx
