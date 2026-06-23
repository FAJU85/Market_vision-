"""Tests for Epic B2 — Saudi trading-calendar guard."""

from __future__ import annotations

from datetime import date

from sqra.trading_calendar import DEFAULT_HOLIDAYS, is_trading_day, is_weekend


def test_weekend_is_friday_and_saturday():
    assert is_weekend(date(2024, 1, 5))  # Friday
    assert is_weekend(date(2024, 1, 6))  # Saturday
    assert not is_weekend(date(2024, 1, 7))  # Sunday (trading)


def test_sunday_through_thursday_are_trading_days():
    # 2024-01-07 (Sun) .. 2024-01-11 (Thu)
    for offset in range(5):
        assert is_trading_day(date(2024, 1, 7 + offset))


def test_national_holiday_is_not_a_trading_day():
    holiday = next(iter(DEFAULT_HOLIDAYS))
    assert not is_trading_day(holiday)


def test_injected_holiday_set_overrides_default():
    custom = date(2024, 7, 1)  # a Monday
    assert is_trading_day(custom)  # trading by default
    assert not is_trading_day(custom, holidays=frozenset({custom}))
