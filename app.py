"""SQRA Gradio dashboard (Epic E1/E2).

Reactive, analytics-first UI (PRD §6 / SRS §4.1). Connects to DuckDB READ_ONLY
for analysis and takes a transient READ_WRITE connection only for discrete
BUY/SELL events. Predictions are read from the serialized cores — the UI never
trains on a click (NFR §7.1).
"""

from __future__ import annotations

import gradio as gr
import plotly.graph_objects as go

from sqra import config, db
from sqra.dashboard_data import DAY_MODE, SWING_MODE, available_symbols, predicted_bounds
from sqra.kpis import max_drawdown, round_trip_pnls, sharpe_ratio, win_loss_ratio
from sqra.schema import DEFAULT_STARTING_CASH
from sqra.simulation import Transaction
from sqra.trading import STRATEGY_KEYS, execute_trade

DEFAULT_SYMBOLS = ["1120", "2222", "1150"]


def _portfolio_frame(conn):
    return conn.execute("SELECT * FROM virtual_portfolio").df()


def _kpi_block(conn, mode_key: str) -> str:
    """Compute Sharpe / Max Drawdown / Win-rate for a strategy from its log."""
    rows = conn.execute(
        "SELECT type, net_cash_impact FROM transaction_history "
        "WHERE strategy_mode = ? ORDER BY timestamp",
        [mode_key],
    ).fetchall()
    txns = [
        Transaction("", None, mode_key, t, 0, 0.0, 0.0, 0.0, float(n))
        for t, n in rows
    ]
    pnls = round_trip_pnls(txns)
    # Equity curve from cumulative realized PnL, for Sharpe / drawdown display.
    equity = [DEFAULT_STARTING_CASH]
    for pnl in pnls:
        equity.append(equity[-1] + pnl)
    return (
        f"**Sharpe:** {sharpe_ratio(equity):.2f}  |  "
        f"**Max DD:** {max_drawdown(equity):.1%}  |  "
        f"**Win rate:** {win_loss_ratio(pnls):.0%}  ({len(pnls)} closed)"
    )


def render_dashboard(symbol: str, strategy_mode: str):
    with db.read_only() as conn:
        df = predicted_bounds(conn, symbol, strategy_mode)
        portfolio = _portfolio_frame(conn)
        mode_key = STRATEGY_KEYS.get(strategy_mode, "DAY_TRADING")
        kpis = _kpi_block(conn, mode_key)

    if df.empty:
        return go.Figure(), portfolio, "No data for this symbol.", kpis

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=df["date"], y=df["close"], name="Close", line=dict(color="#4da3ff"))
    )
    fig.add_trace(
        go.Scatter(x=df["date"], y=df["pred_upper"], name="Upper bound",
                   line=dict(color="green", dash="dash"))
    )
    fig.add_trace(
        go.Scatter(x=df["date"], y=df["pred_lower"], name="Lower bound",
                   line=dict(color="red", dash="dash"))
    )
    fig.update_layout(
        title=f"{symbol} — {strategy_mode}", template="plotly_dark",
        xaxis_rangeslider_visible=False,
    )
    return fig, portfolio, f"Updated for {symbol}.", kpis


def on_trade(strategy_mode: str, symbol: str, action: str, capital: float):
    with db.writable() as conn:
        result = execute_trade(
            conn, strategy_mode=strategy_mode, symbol=symbol, action=action,
            capital_allocation=capital,
        )
    status = f"{action} {symbol}: {result['status']}"
    fig, portfolio, _, kpis = render_dashboard(symbol, strategy_mode)
    return fig, portfolio, status, kpis


def build_ui() -> gr.Blocks:
    with db.read_only() as conn:
        symbols = available_symbols(conn) or DEFAULT_SYMBOLS

    with gr.Blocks(theme=gr.themes.Soft(), title="SQRA") as demo:
        gr.Markdown("# Saudi Quant Retail Alpha (SQRA)")
        with gr.Row():
            with gr.Column(scale=1):
                ticker = gr.Dropdown(symbols, value=symbols[0], label="Tadawul Symbol")
                mode = gr.Radio([DAY_MODE, SWING_MODE], value=DAY_MODE, label="Strategy")
                capital = gr.Slider(1000, 50000, value=10000, step=1000,
                                    label="Capital Allocation (SAR)")
                with gr.Row():
                    buy = gr.Button("BUY", variant="primary")
                    sell = gr.Button("SELL", variant="stop")
                status = gr.Textbox(label="Status", interactive=False)
                kpis = gr.Markdown("")
            with gr.Column(scale=3):
                plot = gr.Plot(label="Price & Predicted Bounds")
                portfolio = gr.Dataframe(label="Virtual Portfolio")

        outputs = [plot, portfolio, status, kpis]
        ticker.change(render_dashboard, [ticker, mode], outputs)
        mode.change(render_dashboard, [ticker, mode], outputs)
        buy.click(lambda m, s, c: on_trade(m, s, "BUY", c), [mode, ticker, capital], outputs)
        sell.click(lambda m, s, c: on_trade(m, s, "SELL", c), [mode, ticker, capital], outputs)
        demo.load(render_dashboard, [ticker, mode], outputs)

    return demo


if __name__ == "__main__":
    config.ensure_data_dir()
    db.initialize_with_recovery()  # F1: recover from a corrupt DB on startup
    build_ui().launch(server_name="0.0.0.0", server_port=7860)
