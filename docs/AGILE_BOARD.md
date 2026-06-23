# SQRA — Agile Board

**Project:** Saudi Quant Retail Alpha (SQRA) — systematic quantitative decision-support
and paper-trading platform for the Saudi Stock Market (Tadawul).

**Stack:** Python · DuckDB · LightGBM · Gradio · Plotly · Hugging Face Pro Space
(persistent storage mounted at `/data`).

**Profile (CLAUDE.md):** Trading Bot / Financial Infrastructure —
Code Quality R/3, Testing R/4, Security R/5, Reliability R/3, Observability R/3,
Performance R/4, Documentation R/2.

> Working protocol: one user story at a time; never skip a subtask's *Done when*
> criteria (it is the acceptance test); every sprint must be demo-able.

---

## Epic A — Foundation & Storage

- **A1** DuckDB schema + init (`saudi_stocks`, `virtual_portfolio`,
  `transaction_history`), composite index `(symbol, date)`, default portfolios seeded.
  - *Done when:* a fresh DB boots and `PRAGMA integrity_check` returns `ok`.
- **A2** Connection-mode discipline: READ_WRITE helper for the cron worker,
  READ_ONLY helper for the app, explicit checkpoint on close.
  - *Done when:* after a short-lived writer closes, a READ_ONLY connection sees
    the committed data, and multiple READ_ONLY connections coexist. (DuckDB takes
    an exclusive lock for a writer, so the design relies on temporal separation,
    not concurrent RW+RO — see Blueprint §III.)
- **A3** HF Space scaffold + persistent `/data` mount + `HF_SECRET_*` secret loading.
  - *Done when:* secrets are read from environment variables; none are hardcoded
    (gitleaks clean).

## Epic B — Ingestion Pipeline (`backend_cron.py`)

- **B1** EOD fetch for Tadawul equities + `^TASI` + Brent crude; `adj_close` calc.
  - *Done when:* rows upserted for ≥200 symbols.
- **B2** Holiday-aware cron `00 16 * * 1-5` with a Saudi trading-calendar guard.
  - *Done when:* a holiday run exits without writing.
- **B3** Outlier defense (modified Z-score; `|Z| > 4.5` + sub-median volume →
  override with previous close, set training sample weight to 0, alert to stderr).
  - *Done when:* a unit test on a synthetic spike confirms override + zero weight.

## Epic C — Dual-Core ML Engine

- **C1** Feature engineering in DuckDB SQL (opening gap, 5-day stochastic,
  50/200-day SMA, TASI-beta-neutralized alpha, Brent co-integration).
  - *Done when:* the feature frame has no look-ahead nulls.
- **C2** **Purged & Embargoed** time-series cross-validation (purge overlapping
  label windows; embargo 5 bars after each test fold).
  - *Done when:* a test proves no train/test temporal overlap.
- **C3** Core A day model (next-day High/Low, MSE) + Core B swing model
  (15-day direction, logloss); serialize to `/data/day_model.txt`, `/data/swing_model.txt`.
  - *Done when:* both models load and predict.
- **C4** Training cadence: nightly incremental day-core (lr `1e-5`), Friday full
  swing sweep; nightly pre-computed predictions cached in DuckDB.
  - *Done when:* the cache table is populated and the UI reads from it.

## Epic D — Paper-Trading Simulation

- **D1** Event-driven row-by-row loop; next-day fill (order at day `t` fills at the
  open of `t+1`); vectorized backtest forbidden.
  - *Done when:* a regression test catches any `t+1 → t` information leak.
- **D2** Friction model: ±0.10% slippage, 0.155% (`0.00155`) commission per leg;
  `NO_ACTION` when projected move < round-trip friction (0.51%).
  - *Done when:* unit tests cover each formula.
- **D3** Trailing stop-loss (−1.5% day / −5.0% swing); UUID transaction audit log.
  - *Done when:* a breach auto-liquidates and logs the transaction.

## Epic E — Gradio UI & KPIs

- **E1** Layout: ticker dropdown, Day/Swing radio, capital slider, BUY/SELL buttons,
  status telemetry.
  - *Done when:* controls render and wire events.
- **E2** Plotly candlestick + predicted upper/lower bounds + trailing-stop lines;
  live `virtual_portfolio` dataframe.
  - *Done when:* the chart updates on ticker/mode change.
- **E3** KPI blocks: Sharpe ratio, Max Drawdown, Win/Loss after friction; UI renders
  in < 1.5s (reads cached predictions, never trains on click).
  - *Done when:* a timing assertion passes.

## Epic F — Hardening & Ship

- **F1** Startup `PRAGMA integrity_check` + schema-recovery path.
  - *Done when:* a corrupted-DB test recovers cleanly.
- **F2** Security gate: no hardcoded secrets, DB outside the public asset dir,
  input validation on trade parameters.
  - *Done when:* gitleaks + Semgrep clean.
- **F3** Test suite ≥ 80% coverage on pure logic (friction, Z-score, CV split);
  README + ADRs.
  - *Done when:* the verification gate is green.

---

## Status

| Epic | Story | Status |
|------|-------|--------|
| A | A1 schema + init | ✅ done |
| A | A2 connection discipline | ✅ done |
| A | A3 HF scaffold + secrets | ✅ done |
| B | B1 EOD ingestion (provider + upsert) | ✅ done |
| B | B2 holiday-aware cron guard | ✅ done |
| B | B3 outlier defense | ✅ done |
| C | C1 feature engineering (DuckDB SQL) | ✅ done |
| C | C2 purged & embargoed CV | ✅ done |
| C | C3 dual-core LightGBM models | ✅ done |
| C | C4 training cadence + prediction cache | ☐ not started |
| D | D1 event-driven loop (next-day fill) | ✅ done |
| D | D2 friction model | ✅ done |
| D | D3 trailing stop-loss + audit log | ✅ done |
| E | E1 Gradio layout + event wiring | ✅ done |
| E | E2 Plotly bounds + portfolio view | ✅ done |
| E | E3 KPI blocks (Sharpe/DD/Win) | ✅ done |
| F | — | ☐ not started |
