"""Real-world execution friction model (Epic D2).

Every synthetic trade is penalized exactly as specified in PRD §5.1 / SRS §3.3.2:

* **Slippage:** buys fill 0.10% above mid, sells 0.10% below mid.
* **Commission:** flat 0.155% (CMA broker mandate) per trade leg.
* **Signal suppression:** if a projected move is smaller than the round-trip
  friction (0.51%), the engine returns ``NO_ACTION``.
* **Trailing stop-loss:** −1.5% (day) / −5.0% (swing) from the position peak.

All functions are pure so each formula is unit-tested in isolation.
"""

from __future__ import annotations

SLIPPAGE_RATE = 0.0010  # 0.10% per leg
COMMISSION_RATE = 0.00155  # 0.155% per leg (CMA)
# Round-trip friction: slippage in + slippage out + two commission legs.
ROUND_TRIP_FRICTION = 2 * SLIPPAGE_RATE + 2 * COMMISSION_RATE  # 0.0051 (0.51%)

STOP_LOSS_PCT = {
    "DAY_TRADING": -0.015,
    "SWING_TRADING": -0.05,
}

NO_ACTION = "NO_ACTION"


def buy_execution_price(mid_price: float) -> float:
    """Price a buy fills at after upward slippage."""
    return mid_price * (1 + SLIPPAGE_RATE)


def sell_execution_price(mid_price: float) -> float:
    """Price a sell fills at after downward slippage."""
    return mid_price * (1 - SLIPPAGE_RATE)


def commission(notional: float) -> float:
    """Brokerage commission on a trade leg's notional value."""
    return abs(notional) * COMMISSION_RATE


def is_actionable(projected_move: float) -> bool:
    """True if the projected fractional move clears round-trip friction."""
    return abs(projected_move) >= ROUND_TRIP_FRICTION


def stop_loss_price(entry_or_peak_price: float, strategy_mode: str) -> float:
    """Absolute stop price for a strategy's trailing threshold."""
    if strategy_mode not in STOP_LOSS_PCT:
        raise ValueError(f"Unknown strategy_mode: {strategy_mode!r}")
    return entry_or_peak_price * (1 + STOP_LOSS_PCT[strategy_mode])
