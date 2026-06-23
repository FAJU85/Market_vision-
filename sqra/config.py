"""Central configuration for SQRA.

All runtime configuration is resolved from environment variables so that no
secrets or environment-specific paths are hardcoded in the repository
(CLAUDE.md §1.3 Security Policy; SRS §5.3). On Hugging Face Spaces, secrets are
injected as ``HF_SECRET_*`` environment variables.
"""

from __future__ import annotations

import os
from pathlib import Path

# Persistent storage root. On HF Pro this is the hard-mounted ``/data`` volume;
# override with ``SQRA_DATA_DIR`` for local development and tests.
DATA_DIR = Path(os.environ.get("SQRA_DATA_DIR", "/data"))

# DuckDB state file. Kept under DATA_DIR (outside any public asset directory) so
# the database cannot be downloaded via the web server (SRS §5.3).
DB_PATH = DATA_DIR / "sqra_storage.db"

# Serialized LightGBM cores.
DAY_MODEL_PATH = DATA_DIR / "day_model.txt"  # Core A upper (next-day high)
DAY_LOW_MODEL_PATH = DATA_DIR / "day_low_model.txt"  # Core A lower (next-day low)
SWING_MODEL_PATH = DATA_DIR / "swing_model.txt"

# Prefix under which Hugging Face injects user-defined secrets.
_HF_SECRET_PREFIX = "HF_SECRET_"


def get_secret(name: str, default: str | None = None) -> str | None:
    """Return a secret injected by Hugging Face as ``HF_SECRET_<NAME>``.

    Looks up ``HF_SECRET_<NAME>`` first, then a bare ``<NAME>`` fallback for
    local development. Never logs the value.
    """
    key = name if name.startswith(_HF_SECRET_PREFIX) else f"{_HF_SECRET_PREFIX}{name}"
    return os.environ.get(key, os.environ.get(name, default))


def require_secret(name: str) -> str:
    """Return a required secret or raise if it is absent."""
    value = get_secret(name)
    if value is None:
        raise RuntimeError(
            f"Required secret {name!r} is not set. Provide it via the "
            f"{_HF_SECRET_PREFIX}{name} environment variable."
        )
    return value


def ensure_data_dir() -> Path:
    """Create the persistent data directory if it does not yet exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR
