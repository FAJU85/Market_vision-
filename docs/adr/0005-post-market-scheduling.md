# ADR-0005: Post-market scheduling on Hugging Face Spaces

- **Status:** Accepted
- **Date:** 2026-06-23

## Context

The ingestion + training cycle must run daily at 16:00 AST on Tadawul trading
days (PRD §4.1). Hugging Face Spaces provide no native cron scheduler, and the
project's `.github/workflows` are an off-limits zone (CLAUDE.md), so an external
GitHub Actions schedule is out of scope here.

## Decision

Drive the cycle from a lightweight in-process scheduler (`sqra/scheduler.py`):
a loop polls the clock once a minute and triggers `backend_cron.run()` when
`is_due(now, last_run)` returns true — at/after 16:00 AST, on a trading day,
once per day. The scheduling decision and a single `tick` are pure and
unit-tested; `run_forever` is the thin polling wrapper.

Run it as a **dedicated worker process** (`python -m sqra.scheduler`) so it
remains the sole DB writer, consistent with the single-writer model
(ADR-0002). The Gradio app stays read-only.

## Consequences

- No external scheduler dependency; works inside a single persistent Space.
- Because DuckDB forbids concurrent RW+RO in one process, the scheduler must run
  separately from `app.py` (or as the only writer) to avoid lock contention.
- Polling granularity is one minute — adequate for a daily post-market job.
- Hijri holidays still come from the injectable calendar (ADR none; see
  `trading_calendar`); update that set annually.
