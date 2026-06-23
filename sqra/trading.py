"""Database-backed single trade execution (Epic D — UI event path).

This is the transactional path invoked by a user clicking BUY/SELL in the Gradio
UI (SRS §4.1.1). It takes a transient READ_WRITE connection, applies the friction
model, updates ``virtual_portfolio``, and appends to ``transaction_history``.

It deliberately corrects three defects in the original Blueprint ``app.py``:

1. **SQL injection** — every value is bound as a parameter; no f-string SQL.
2. **Partial-position SELL** — sells respect a requested share count instead of
   always liquidating the entire position.
3. **avg-cost on full exit** — average cost resets only when the position is
   fully closed.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

import duckdb

from .friction import buy_execution_price, commission, sell_execution_price

STRATEGY_KEYS = {
    "Day Trading Core": "DAY_TRADING",
    "Swing Trading Core": "SWING_TRADING",
}

# Tadawul symbols are numeric tickers; allow a small alphanumeric superset.
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9]{1,12}$")


def is_valid_symbol(symbol: str) -> bool:
    """Validate a ticker before it is used in any query (defense in depth)."""
    return isinstance(symbol, str) and bool(_SYMBOL_RE.match(symbol))


def _latest_price(conn: duckdb.DuckDBPyConnection, symbol: str) -> float | None:
    row = conn.execute(
        "SELECT close FROM saudi_stocks WHERE symbol = ? ORDER BY date DESC LIMIT 1",
        [symbol],
    ).fetchone()
    return None if row is None else float(row[0])


def execute_trade(
    conn: duckdb.DuckDBPyConnection,
    *,
    strategy_mode: str,
    symbol: str,
    action: str,
    capital_allocation: float = 0.0,
    sell_shares: int | None = None,
) -> dict:
    """Execute one BUY or SELL against the virtual portfolio.

    ``strategy_mode`` accepts either a UI label ("Day Trading Core") or a raw key
    ("DAY_TRADING"). Returns a result dict describing the outcome.
    """
    mode_key = STRATEGY_KEYS.get(strategy_mode, strategy_mode)
    if mode_key not in STRATEGY_KEYS.values():
        raise ValueError(f"Unknown strategy_mode: {strategy_mode!r}")
    if action not in ("BUY", "SELL"):
        raise ValueError(f"Unknown action: {action!r}")
    if not is_valid_symbol(symbol):
        return {"status": "INVALID_SYMBOL", "symbol": symbol}
    if action == "BUY" and capital_allocation <= 0:
        return {"status": "INVALID_CAPITAL", "symbol": symbol}
    if sell_shares is not None and sell_shares <= 0:
        return {"status": "INVALID_QUANTITY", "symbol": symbol}

    row = conn.execute(
        "SELECT cash_balance, shares_held, avg_purchase_price "
        "FROM virtual_portfolio WHERE strategy_mode = ?",
        [mode_key],
    ).fetchone()
    if row is None:
        raise ValueError(f"No portfolio for {mode_key}")
    cash, shares, avg_cost = float(row[0]), int(row[1]), float(row[2])

    mid = _latest_price(conn, symbol)
    if mid is None:
        return {"status": "NO_DATA", "symbol": symbol}

    if action == "BUY":
        exec_price = buy_execution_price(mid)
        budget = min(capital_allocation, cash)
        qty = int(budget // exec_price)
        while qty > 0 and qty * exec_price + commission(qty * exec_price) > cash:
            qty -= 1
        if qty <= 0:
            return {"status": "INSUFFICIENT_FUNDS", "symbol": symbol}
        gross = qty * exec_price
        comm = commission(gross)
        total_cost = gross + comm
        new_cash = cash - total_cost
        new_shares = shares + qty
        new_avg = (shares * avg_cost + gross) / new_shares
        net_impact = -total_cost
        txn_shares = qty
    else:  # SELL
        if shares <= 0:
            return {"status": "NO_POSITION", "symbol": symbol}
        qty = shares if sell_shares is None else min(sell_shares, shares)
        if qty <= 0:
            return {"status": "INVALID_QUANTITY", "symbol": symbol}
        exec_price = sell_execution_price(mid)
        gross = qty * exec_price
        comm = commission(gross)
        net = gross - comm
        new_cash = cash + net
        new_shares = shares - qty
        # Average cost is preserved on a partial exit; reset only when flat.
        new_avg = avg_cost if new_shares > 0 else 0.0
        net_impact = net
        txn_shares = qty

    conn.execute(
        "UPDATE virtual_portfolio SET cash_balance = ?, shares_held = ?, "
        "avg_purchase_price = ?, asset_symbol = ?, last_updated = ? "
        "WHERE strategy_mode = ?",
        [new_cash, new_shares, new_avg, symbol if new_shares > 0 else "CASH",
         datetime.now(), mode_key],
    )
    conn.execute(
        "INSERT INTO transaction_history VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            str(uuid.uuid4()), datetime.now(), mode_key, symbol, action,
            txn_shares, exec_price, abs(mid - exec_price) * txn_shares, comm, net_impact,
        ],
    )
    return {
        "status": "FILLED",
        "action": action,
        "symbol": symbol,
        "shares": txn_shares,
        "execution_price": exec_price,
        "cash_balance": new_cash,
        "shares_held": new_shares,
    }
