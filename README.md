---
title: Saudi Quant Retail Alpha (SQRA)
emoji: 📈
colorFrom: green
colorTo: blue
sdk: gradio
sdk_version: 6.19.0
app_file: app.py
pinned: false
---

# Saudi Quant Retail Alpha (SQRA)

A systematic quantitative **decision-support and paper-trading** platform for the
Saudi Stock Market (Tadawul). SQRA converts end-of-day market mechanics and macro
data into statistically validated trading ranges for short-term (day) and
medium-term (swing) horizons. It is a **manual decision-support tool only** — it
does not route live broker orders.

> ⚠️ Educational/research use. Not investment advice.

## Architecture

Strict decoupling avoids DuckDB's single-writer crashes (see
[ADR-0002](docs/adr/0002-duckdb-single-writer.md)):

```
backend_cron.py  ──(READ_WRITE, 16:00 AST)──►  /data/sqra_storage.db  ◄──(READ_ONLY)──  app.py (Gradio)
   ingestion + LightGBM training                    DuckDB                  dashboard + trade events
```

| Layer | Technology |
|------|------------|
| Hosting | Hugging Face Pro Space (persistent `/data`) |
| Storage | DuckDB (embedded OLAP) |
| ML | LightGBM (dual core: day + swing) |
| UI | Gradio + Plotly |

## Project layout

```
sqra/
├── config.py            # env-based config & HF_SECRET_* loading
├── schema.py            # DuckDB schema + integrity check
├── db.py                # connection discipline + recovery (F1)
├── ingest.py            # EOD ingestion (provider abstraction)
├── outliers.py          # modified Z-score outlier defense
├── trading_calendar.py  # Tadawul Sun–Thu calendar
├── features.py          # DuckDB SQL feature engineering
├── cross_validation.py  # purged & embargoed CV
├── models.py            # dual-core LightGBM train/load/predict
├── friction.py          # slippage / commission / stop-loss
├── simulation.py        # event-driven paper-trading loop
├── trading.py           # DB-backed single-trade executor
├── kpis.py              # Sharpe / drawdown / win-rate
└── dashboard_data.py    # READ_ONLY prediction overlay
app.py                   # Gradio dashboard
backend_cron.py          # post-market ingestion + training worker
```

## Setup

```bash
pip install -r requirements-dev.txt
cp .env.example .env          # then fill in secrets
```

Secrets are read from `HF_SECRET_*` environment variables (Space secrets); see
[ADR-0004](docs/adr/0004-secrets-via-env.md). Never commit credentials.

## Run

```bash
python backend_cron.py        # ingest + train (writer); runs once
python app.py                 # launch the dashboard (reader) on :7860
```

By default the worker uses an offline `MockProvider`. Set `SQRA_LIVE_DATA=1` to
fetch real adjusted EOD bars (Tadawul equities + `^TASI` + Brent) via Yahoo
Finance; failures retry then fall back without crashing the cron.

On Hugging Face Spaces, `app.py` is the entry point. The ingestion worker is
scheduled for `00 16 * * 1-5` (16:00 AST, Sun–Thu trading days) — see
[ADR-0003](docs/adr/0003-purged-embargoed-cv.md) for the modelling guardrails.

## Verification gate

```bash
ruff check sqra tests app.py backend_cron.py
pytest --cov=sqra --cov-report=term-missing      # target >= 80%
```

## Documentation

- [Agile board](docs/AGILE_BOARD.md) — epic/story breakdown and status.
- [Architecture Decision Records](docs/adr/) — significant decisions.
