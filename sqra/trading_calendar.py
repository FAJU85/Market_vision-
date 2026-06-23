"""Saudi (Tadawul) trading-calendar guard (Epic B2).

Tadawul trades Sunday through Thursday; Friday and Saturday are the weekend.
The ingestion cron (PRD §4.1 / SRS §3.1.2) must skip weekends and Saudi national
holidays. Eid and other Hijri-based holidays shift each year, so the holiday set
is injectable; a small set of fixed-date observances is provided as a default.
"""

from __future__ import annotations

from datetime import date

# Tadawul weekend: Friday (4) and Saturday (5) in Python's Monday=0 convention.
_WEEKEND = {4, 5}

# Fixed-date Saudi observances. Hijri holidays (Eid al-Fitr, Eid al-Adha) move
# annually and should be supplied via the ``holidays`` argument.
DEFAULT_HOLIDAYS: frozenset[date] = frozenset(
    {
        date(2024, 9, 23),  # Saudi National Day
        date(2025, 9, 23),
        date(2026, 9, 23),
        date(2024, 2, 22),  # Founding Day
        date(2025, 2, 22),
        date(2026, 2, 22),
    }
)


def is_weekend(day: date) -> bool:
    """Return True if ``day`` falls on the Tadawul weekend (Fri/Sat)."""
    return day.weekday() in _WEEKEND


def is_trading_day(day: date, holidays: frozenset[date] | None = None) -> bool:
    """Return True if Tadawul is open on ``day``."""
    holiday_set = DEFAULT_HOLIDAYS if holidays is None else holidays
    return not is_weekend(day) and day not in holiday_set
