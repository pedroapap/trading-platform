"""Performance metrics of a backtest, from its equity curve and its trades."""

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from app.backtest.engine import BacktestConfig, BacktestResult, SimulatedTrade

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


def daily_returns(equity: pd.Series) -> pd.Series:
    """Returns between consecutive daily closes of the equity curve. Days are UTC; days
    without bars are skipped."""
    closes = equity.resample("1D").last().dropna()
    return closes.pct_change().dropna()


# `periods_per_year` annualizes daily ratios: 365 where markets trade every day (crypto), 252
# for stock exchanges. The risk-free rate is taken as zero.


def sharpe_ratio(equity: pd.Series, periods_per_year: int = 365) -> float | None:
    """Annualized Sharpe ratio of the daily returns. None with fewer than two daily returns
    or when they never vary."""
    returns = daily_returns(equity)
    if len(returns) < 2:
        return None
    return _annualized(returns.mean(), returns.std(), periods_per_year)


def sortino_ratio(equity: pd.Series, periods_per_year: int = 365) -> float | None:
    """Annualized Sortino ratio of the daily returns: the mean over the downside deviation,
    the root mean square of the losing days' returns counted over all days (as empyrical
    computes it). None with fewer than two daily returns or without a losing day."""
    returns = daily_returns(equity)
    if len(returns) < 2:
        return None
    downside = math.sqrt((returns.clip(upper=0) ** 2).mean())
    return _annualized(returns.mean(), downside, periods_per_year)


def _annualized(mean: float, deviation: float, periods_per_year: int) -> float | None:
    if deviation == 0:
        return None
    ratio = float(mean / deviation * math.sqrt(periods_per_year))
    return ratio if math.isfinite(ratio) else None


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


@dataclass(frozen=True)
class Benchmark:
    """Buying at the first bar's open with all of the initial capital, at the backtest's fee
    and slippage, and holding to the end: what a strategy has to beat. Its equity is marked to
    market at each close (the last one after selling); its return, CAGR and drawdown count
    from the initial capital."""

    equity: pd.Series
    return_pct: float
    cagr_pct: float | None
    max_drawdown_pct: float


def buy_and_hold(bars: pd.DataFrame, config: BacktestConfig) -> Benchmark:
    """Buy and hold over `bars`, at the costs of `config`."""
    fee, slip = config.fee_pct / 100, config.slippage_pct / 100
    # As for a trade, the capital pays for the notional and its entry fee, so none is left.
    notional = config.initial_capital / (1 + fee)
    size = notional / (bars["open"].iloc[0] * (1 + slip))
    equity = size * bars["close"].astype(float)
    equity.iloc[-1] = size * bars["close"].iloc[-1] * (1 - slip) * (1 - fee)
    from_capital = pd.concat([pd.Series([config.initial_capital], index=bars.index[:1]), equity])
    return Benchmark(
        equity=equity,
        return_pct=total_return_pct(from_capital),
        cagr_pct=cagr_pct(from_capital),
        max_drawdown_pct=max_drawdown_pct(from_capital),
    )


@dataclass(frozen=True)
class Metrics:
    """Every metric of a backtest; see the functions above for definitions."""

    total_return_pct: float
    cagr_pct: float | None
    max_drawdown_pct: float
    sharpe_ratio: float | None
    sortino_ratio: float | None
    num_trades: int
    win_rate_pct: float | None
    profit_factor: float | None
    expectancy: float | None
    average_win: float | None
    average_loss: float | None
    exposure_pct: float
    # Buy and hold over the same bars (see `Benchmark`); None for runs made before it was.
    buy_and_hold_return_pct: float | None = None
    buy_and_hold_cagr_pct: float | None = None
    buy_and_hold_max_drawdown_pct: float | None = None


def summarize(
    result: BacktestResult, periods_per_year: int = 365, benchmark: Benchmark | None = None
) -> Metrics:
    equity = result.equity
    compared = {}
    if benchmark is not None:
        compared = {
            "buy_and_hold_return_pct": benchmark.return_pct,
            "buy_and_hold_cagr_pct": benchmark.cagr_pct,
            "buy_and_hold_max_drawdown_pct": benchmark.max_drawdown_pct,
        }
    return Metrics(
        total_return_pct=total_return_pct(equity),
        cagr_pct=cagr_pct(equity),
        max_drawdown_pct=max_drawdown_pct(equity),
        sharpe_ratio=sharpe_ratio(equity, periods_per_year),
        sortino_ratio=sortino_ratio(equity, periods_per_year),
        **asdict(trade_stats(result.trades, equity.index)),
        **compared,
    )
