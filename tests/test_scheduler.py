"""Tests for the post-market scheduler (backlog #3)."""

from __future__ import annotations

from datetime import date, datetime

from sqra.scheduler import AST, is_due, tick


def _at(year, month, day, hour):
    return datetime(year, month, day, hour, 0, tzinfo=AST)


# 2024-01-07 is a Sunday (Tadawul trading day); 2024-01-06 a Saturday (weekend).


def test_due_at_schedule_hour_on_trading_day():
    assert is_due(_at(2024, 1, 7, 16), last_run_date=None) is True


def test_not_due_before_schedule_hour():
    assert is_due(_at(2024, 1, 7, 15), last_run_date=None) is False


def test_not_due_on_weekend():
    assert is_due(_at(2024, 1, 6, 17), last_run_date=None) is False


def test_not_due_if_already_ran_today():
    today = date(2024, 1, 7)
    assert is_due(_at(2024, 1, 7, 17), last_run_date=today) is False


def test_tick_runs_runner_once_when_due():
    calls = []
    last = tick(_at(2024, 1, 7, 16), None, lambda **kw: calls.append(kw["today"]))
    assert calls == [date(2024, 1, 7)]
    assert last == date(2024, 1, 7)

    # Same day again: idempotent, runner not called a second time.
    last2 = tick(_at(2024, 1, 7, 18), last, lambda **kw: calls.append(kw["today"]))
    assert calls == [date(2024, 1, 7)]
    assert last2 == last


def test_tick_does_not_run_when_not_due():
    calls = []
    last = tick(_at(2024, 1, 7, 9), None, lambda **kw: calls.append(kw["today"]))
    assert calls == []
    assert last is None
