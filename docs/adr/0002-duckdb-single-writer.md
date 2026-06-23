# ADR-0002: DuckDB single-writer isolation

- **Status:** Accepted
- **Date:** 2026-06-23

## Context

DuckDB permits only one read-write process and takes an exclusive lock on the
database file. A naive design where both the Gradio app and the ingestion worker
write concurrently causes `IOException: Could not set lock on file` crashes
(SRS §2.2). The Blueprint (§III) flags this as the primary production risk.

## Decision

Segregate connections strictly:

- `backend_cron.py` is the **only** writer, holding a short-lived READ_WRITE
  connection during the post-market window.
- `app.py` connects READ_ONLY for analysis and takes a transient writable
  connection only for discrete user BUY/SELL events.

Helpers `db.writable()` / `db.read_only()` enforce this and checkpoint on close.
Within a single process, mixed RW+RO connections are not attempted (DuckDB
forbids it); the design relies on temporal separation, not concurrency.

## Consequences

- No lock-contention crashes under the intended workload.
- True high-concurrency write access would require migrating to Postgres/SQLite
  with WAL — deferred; documented as a future scaling path.
