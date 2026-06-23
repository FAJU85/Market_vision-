"""Post-market background worker (Epic B entrypoint).

Runs daily at 16:00 AST (cron ``00 16 * * 1-5``) per PRD §4.1. Skips Saudi
holidays, then ingests EOD market data inside a short-lived READ_WRITE DuckDB
connection. ML training (Epic C) will be wired in here once implemented.

This worker is the *only* writer to the database (SRS §2.2).
"""

from __future__ import annotations

import os
import sys
from datetime import date

from sqra import db
from sqra.cache import run_training_cycle
from sqra.ingest import MarketDataProvider, MockProvider, ingest_market_data
from sqra.live_provider import YahooProvider
from sqra.trading_calendar import is_trading_day

# Placeholder universe; replaced by the full Tadawul listing once the live feed
# is configured with the broader index membership.
DEFAULT_SYMBOLS = ["1120", "2222", "1150"]


def _default_provider() -> MarketDataProvider:
    """Live provider when SQRA_LIVE_DATA is truthy, else the offline mock."""
    if os.environ.get("SQRA_LIVE_DATA", "").lower() in ("1", "true", "yes"):
        return YahooProvider()
    return MockProvider()


def run(
    *,
    today: date | None = None,
    provider: MarketDataProvider | None = None,
    symbols: list[str] | None = None,
    train: bool = True,
) -> dict:
    """Execute one post-market cycle: ingest, then (optionally) train + cache.

    Returns a summary dict; ``rows`` is 0 when markets are closed.
    """
    day = today or date.today()
    if not is_trading_day(day):
        print(f"[cron] {day} is not a Tadawul trading day; skipping.", file=sys.stderr)
        return {"rows": 0, "skipped": True}

    db.initialize_with_recovery()  # F1: recover from a corrupt DB on startup
    market_provider = provider or _default_provider()
    universe = symbols or DEFAULT_SYMBOLS

    with db.writable() as conn:
        rows = ingest_market_data(conn, market_provider, universe)
        summary = {"rows": rows, "skipped": False}
        if train:
            summary.update(run_training_cycle(conn, today=day))
    print(f"[cron] ingested {rows} bars for {len(universe)} symbols on {day}: {summary}")
    return summary


if __name__ == "__main__":
    run()
