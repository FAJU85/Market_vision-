"""Post-market background worker (Epic B entrypoint).

Runs daily at 16:00 AST (cron ``00 16 * * 1-5``) per PRD §4.1. Skips Saudi
holidays, then ingests EOD market data inside a short-lived READ_WRITE DuckDB
connection. ML training (Epic C) will be wired in here once implemented.

This worker is the *only* writer to the database (SRS §2.2).
"""

from __future__ import annotations

import sys
from datetime import date

from sqra import db
from sqra.ingest import MarketDataProvider, MockProvider, ingest_market_data
from sqra.trading_calendar import is_trading_day

# Placeholder universe; replaced by the full Tadawul listing once a real
# provider is connected (Epic B1 follow-up).
DEFAULT_SYMBOLS = ["1120", "2222", "1150"]


def run(
    *,
    today: date | None = None,
    provider: MarketDataProvider | None = None,
    symbols: list[str] | None = None,
) -> int:
    """Execute one ingestion cycle. Returns rows written (0 if markets closed)."""
    day = today or date.today()
    if not is_trading_day(day):
        print(f"[cron] {day} is not a Tadawul trading day; skipping.", file=sys.stderr)
        return 0

    db.initialize()
    market_provider = provider or MockProvider()
    universe = symbols or DEFAULT_SYMBOLS

    with db.writable() as conn:
        rows = ingest_market_data(conn, market_provider, universe)
    print(f"[cron] ingested {rows} bars for {len(universe)} symbols on {day}.")
    return rows


if __name__ == "__main__":
    run()
