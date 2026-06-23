# ADR-0004: Secrets via environment variables

- **Status:** Accepted
- **Date:** 2026-06-23

## Context

The system needs market-data provider credentials. CLAUDE.md §1.3 and SRS §5.3
prohibit hardcoded credentials and require secret-scanner-clean code.

## Decision

All secrets are read from `HF_SECRET_*` environment variables via
`config.get_secret()` / `config.require_secret()`, with a bare-name fallback for
local development. `.env` is git-ignored; `.env.example` documents the variables.
The DuckDB file lives under `/data` (outside any public asset directory) so it
cannot be downloaded via the web server.

## Consequences

- No credentials in version control; secret-scan gate stays green.
- Rotating a credential is a Space-settings change, not a code change.

## Deviation note

The SRS specifies `PRAGMA integrity_check`, which is SQLite-only syntax. DuckDB
has no equivalent, so `schema.integrity_ok()` verifies that every core table is
scannable instead. Recorded here for traceability.
