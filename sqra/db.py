"""DuckDB connection discipline (Epic A2).

DuckDB allows only a single writer process. To avoid
``IOException: Could not set lock on file`` crashes (SRS §2.2), connection types
are strictly segregated:

* The ingestion/training worker (``backend_cron.py``) opens short-lived
  READ_WRITE connections via :func:`writable`.
* The Gradio app (``app.py``) opens READ_ONLY connections via :func:`read_only`,
  taking a transient writable connection only for discrete user trade events.

Both context managers checkpoint and close on exit so the write-ahead log is
merged back into the main database file (SRS §4.2).
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb

from . import config
from .schema import create_schema, integrity_ok, seed_default_portfolios


def initialize(db_path: Path | str | None = None) -> Path:
    """Create the database file, schema, and default portfolios.

    Returns the resolved database path. Safe to call repeatedly.
    """
    path = Path(db_path) if db_path is not None else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(path))
    try:
        create_schema(conn)
        seed_default_portfolios(conn)
        if not integrity_ok(conn):
            raise RuntimeError(f"Integrity check failed for {path}")
    finally:
        conn.close()
    return path


def initialize_with_recovery(db_path: Path | str | None = None) -> Path:
    """Initialize the database, recovering from a corrupt file (F1, SRS §5.2).

    On startup the schema is verified. If the file cannot be opened or fails the
    integrity check, the corrupt file is moved aside (``*.corrupt``) and a fresh
    schema is recreated, so the container always boots into a usable state.
    """
    path = Path(db_path) if db_path is not None else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return initialize(path)
    except (duckdb.Error, RuntimeError) as exc:
        if path.exists():
            quarantine = path.with_suffix(path.suffix + ".corrupt")
            quarantine.unlink(missing_ok=True)
            path.rename(quarantine)
            print(
                f"[recovery] {path} was corrupt ({exc}); moved to {quarantine} "
                f"and recreated empty schema.",
                file=sys.stderr,
            )
        return initialize(path)


@contextmanager
def writable(db_path: Path | str | None = None) -> Iterator[duckdb.DuckDBPyConnection]:
    """Yield a short-lived READ_WRITE connection, checkpointing on close."""
    path = Path(db_path) if db_path is not None else config.DB_PATH
    conn = duckdb.connect(str(path), read_only=False)
    try:
        yield conn
        conn.execute("CHECKPOINT")
    finally:
        conn.close()


@contextmanager
def read_only(db_path: Path | str | None = None) -> Iterator[duckdb.DuckDBPyConnection]:
    """Yield a READ_ONLY connection for the UI / analytics path."""
    path = Path(db_path) if db_path is not None else config.DB_PATH
    conn = duckdb.connect(str(path), read_only=True)
    try:
        yield conn
    finally:
        conn.close()
