"""Performance metrics of a backtest, from its equity curve and its trades."""

import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.backtest.engine import SimulatedTrade

YEAR = pd.Timedelta(days=365.25)


def total_return_pct(equity: pd.Series) -> float:
    """Change from the first to the last equity value, in percent."""
    return float((equity.iloc[-1] / equity.iloc[0] - 1) * 100)


def cagr_pct(equity: pd.Series) -> float | None:
    """Compound annual growth rate over the time the equity curve spans, in percent: -100
    once the equity is gone, None when the curve spans no time or annualizing a very short
    span overflows."""
    years = (equity.index[-1] - equity.index[0]) / YEAR
    if years <= 0:
        return None
    growth = equity.iloc[-1] / equity.iloc[0]
    if growth <= 0:
        return -100.0
    try:
        cagr = (float(growth) ** (1 / years) - 1) * 100
    except OverflowError:
        return None
    return cagr if math.isfinite(cagr) else None


def max_drawdown_pct(equity: pd.Series) -> float:
    """The largest fall from a running peak, as a percentage of that peak; 0 when equity
    never falls."""
    peaks = equity.cummax()
    return float(((peaks - equity) / peaks).max() * 100)


@dataclass(frozen=True)
class TradeStats:
    num_trades: int
    # Share of trades with a positive P&L, in percent.
    win_rate_pct: float | None
    # Gross profit over gross loss; None without a losing trade.
    profit_factor: float | None
    # Average P&L per trade.
    expectancy: float | None
    average_win: float | None
    # Negative, like the P&L of the trades it averages.
    average_loss: float | None
    # Share of bars on which a position was open at some point, entry and exit bars included
    # (as backtesting.py counts it), in percent.
    exposure_pct: float


def trade_stats(trades: Sequence[SimulatedTrade], index: pd.DatetimeIndex) -> TradeStats:
    """Statistics of `trades` made on bars with timestamps `index`. P&L is net of costs."""
    pnls = np.array([trade.pnl for trade in trades], dtype=float)
    wins, losses = pnls[pnls > 0], pnls[pnls < 0]
    held = np.zeros(len(index), dtype=bool)
    for trade in trades:
        held[index.get_loc(trade.entry_time) : index.get_loc(trade.exit_time) + 1] = True
    win_rate = _mean(pnls > 0)
    return TradeStats(
        num_trades=len(pnls),
        win_rate_pct=None if win_rate is None else win_rate * 100,
        profit_factor=float(wins.sum() / -losses.sum()) if len(losses) else None,
        expectancy=_mean(pnls),
        average_win=_mean(wins),
        average_loss=_mean(losses),
        exposure_pct=float(held.mean() * 100) if len(index) else 0.0,
    )


def _mean(values: np.ndarray) -> float | None:
    return float(values.mean()) if len(values) else None
