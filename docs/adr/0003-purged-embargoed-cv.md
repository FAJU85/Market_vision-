# ADR-0003: Purged & embargoed cross-validation

- **Status:** Accepted
- **Date:** 2026-06-23

## Context

The swing target spans a 15-day forward horizon and features include rolling
SMAs. Standard K-Fold cross-validation leaks future information through
overlapping label windows and autoregressive memory, inflating backtest metrics
(PRD §4.2, SRS §3.2.3).

## Decision

Use **purged & embargoed** time-series CV (de Prado), implemented in
`sqra/cross_validation.py`:

- **Purge** training observations whose label window `[i, i + horizon]` overlaps
  the test fold.
- **Embargo** a fixed number of bars (default 5) immediately after each test
  fold.

The event-driven simulation (`sqra/simulation.py`) likewise forbids vectorized
backtesting and fills orders at the next bar's open, so no information flows from
`t+1` back to `t`.

## Consequences

- Backtest metrics reflect genuinely out-of-sample performance.
- Slightly smaller effective training sets due to purged/embargoed bars.
