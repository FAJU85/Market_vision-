# ADR-0001: Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-06-23

## Context

The CLAUDE.md operating standard (Documentation R/2 for the Trading Bot profile)
requires significant architectural decisions to be recorded as ADRs.

## Decision

We keep lightweight Markdown ADRs under `docs/adr/`, numbered sequentially. Each
records context, the decision, and its consequences.

## Consequences

- A durable rationale trail for future contributors and agents.
- Each non-trivial dependency or structural choice gets one ADR.
