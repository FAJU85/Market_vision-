"""Post-market scheduler (deferred backlog #3).

Hugging Face Spaces have no native cron, so the post-market cycle is driven by a
lightweight in-process scheduler: a loop polls the clock and triggers
``backend_cron.run`` once per trading day at/after 16:00 AST (PRD §4.1).

The scheduling decision (:func:`is_due`) and a single :func:`tick` are pure and
unit-tested; ``run_forever`` is the thin polling wrapper. Run it as a dedicated
worker process so it remains the sole DB writer (see ADR-0005).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .trading_calendar import is_trading_day

AST = ZoneInfo("Asia/Riyadh")
SCHEDULE_HOUR = 16  # 16:00 AST, after the Tadawul closing auction settles.


def is_due(
    now: datetime,
    last_run_date: date | None,
    *,
    schedule_hour: int = SCHEDULE_HOUR,
    holidays=None,
) -> bool:
    """True if the post-market cycle should run at ``now`` (assumed AST).

    Conditions: a Tadawul trading day, at or after ``schedule_hour``, and not
    already run today.
    """
    today = now.date()
    if not is_trading_day(today, holidays):
        return False
    if now.hour < schedule_hour:
        return False
    return last_run_date != today


def tick(
    now: datetime,
    last_run_date: date | None,
    runner: Callable[..., object],
    *,
    schedule_hour: int = SCHEDULE_HOUR,
) -> date | None:
    """Run ``runner`` once if due; return the (possibly updated) last-run date."""
    if is_due(now, last_run_date, schedule_hour=schedule_hour):
        runner(today=now.date())
        return now.date()
    return last_run_date


def run_forever(
    runner: Callable[..., object] | None = None,
    *,
    poll_seconds: int = 60,
    schedule_hour: int = SCHEDULE_HOUR,
    max_iterations: int | None = None,
) -> None:
    """Poll the clock and trigger the post-market cycle when due.

    ``max_iterations`` bounds the loop for tests; ``None`` runs indefinitely.
    """
    import backend_cron

    run = runner or backend_cron.run
    last_run_date: date | None = None
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        now = datetime.now(AST)
        last_run_date = tick(now, last_run_date, run, schedule_hour=schedule_hour)
        iterations += 1
        if max_iterations is None or iterations < max_iterations:
            time.sleep(poll_seconds)


if __name__ == "__main__":
    run_forever()
