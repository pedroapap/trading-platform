import pandas as pd
import pytest

from app.backtest import metrics
from app.backtest.engine import SimulatedTrade
from app.enums import Direction, ExitReason


def curve(values: list[float], freq: str = "D") -> pd.Series:
    return pd.Series(
        values, index=pd.date_range("2026-01-01", periods=len(values), freq=freq, tz="UTC")
    )


def test_total_return():
    assert metrics.total_return_pct(curve([100, 110, 99, 120])) == pytest.approx(20)


def test_max_drawdown_is_the_largest_percentage_fall():
    # 200 -> 120 loses more money (80), but 100 -> 50 is the larger fall: 50%.
    assert metrics.max_drawdown_pct(curve([100, 50, 200, 120])) == 50


def test_max_drawdown_is_zero_when_equity_never_falls():
    assert metrics.max_drawdown_pct(curve([100, 100, 110, 120])) == 0


def test_max_drawdown_can_exceed_100_percent_when_equity_goes_negative():
    assert metrics.max_drawdown_pct(curve([100, -50])) == 150


def years_apart(first: float, last: float, years: float) -> pd.Series:
    start = pd.Timestamp("2024-01-01", tz="UTC")
    return pd.Series([first, last], index=[start, start + pd.Timedelta(days=365.25 * years)])


def test_cagr():
    # 100 -> 121 over two years is 10% a year.
    assert metrics.cagr_pct(years_apart(100, 121, years=2)) == pytest.approx(10)


def test_cagr_of_a_loss():
    assert metrics.cagr_pct(years_apart(100, 50, years=1)) == pytest.approx(-50)


def test_cagr_once_equity_is_gone():
    assert metrics.cagr_pct(curve([100, 20, -5])) == -100


def test_cagr_needs_time_to_pass():
    assert metrics.cagr_pct(curve([100])) is None


def test_cagr_of_a_very_short_span_is_not_annualized_to_infinity():
    # Doubling in a minute would compound to about 2 ** 525,960 a year.
    assert metrics.cagr_pct(curve([100, 200], freq="min")) is None


TEN_BARS = pd.date_range("2026-01-01", periods=10, freq="min", tz="UTC")


def trade(pnl: float, entry: int, exit_: int) -> SimulatedTrade:
    """A trade with the given P&L, held from bar `entry` to bar `exit_` of TEN_BARS."""
    return SimulatedTrade(
        direction=Direction.LONG,
        entry_time=TEN_BARS[entry],
        entry_price=100,
        exit_time=TEN_BARS[exit_],
        exit_price=100 + pnl,
        size=1,
        entry_fee=0,
        exit_fee=0,
        slippage=0,
        pnl=pnl,
        pnl_pct=pnl,
        exit_reason=ExitReason.SIGNAL,
    )


def test_trade_stats_by_hand():
    trades = [
        trade(100, 0, 1),
        trade(-50, 2, 2),
        trade(0, 3, 4),  # breakeven: neither a win nor a loss
        trade(200, 5, 5),
        trade(-25, 7, 8),
    ]

    assert metrics.trade_stats(trades, TEN_BARS) == metrics.TradeStats(
        num_trades=5,
        win_rate_pct=40,  # 2 of 5
        profit_factor=4,  # (100 + 200) / (50 + 25)
        expectancy=45,  # 225 / 5
        average_win=150,
        average_loss=-37.5,
        exposure_pct=80,  # bars 0-5, 7 and 8 of 10
    )


def test_trade_stats_without_trades():
    assert metrics.trade_stats([], TEN_BARS) == metrics.TradeStats(
        num_trades=0,
        win_rate_pct=None,
        profit_factor=None,
        expectancy=None,
        average_win=None,
        average_loss=None,
        exposure_pct=0,
    )


def test_trade_stats_without_losses():
    stats = metrics.trade_stats([trade(10, 0, 1), trade(30, 2, 3)], TEN_BARS)

    assert (stats.win_rate_pct, stats.average_win) == (100, 20)
    assert stats.profit_factor is None
    assert stats.average_loss is None
