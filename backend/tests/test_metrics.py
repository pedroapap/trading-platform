import math
from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest
from pydantic import TypeAdapter

from app.backtest import metrics
from app.backtest.engine import BacktestConfig, BacktestResult, SimulatedTrade, simulate
from app.enums import Direction, ExitReason
from tests.helpers import random_bars


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
        # Returns of 100, -50, 0, 200 and -25 (in percent): a mean of 45, whose squared
        # deviations sum to 43,000, a sample variance of 10,750.
        average_trade_pct=45,
        average_trade_margin_pct=pytest.approx(1.96 * math.sqrt(10_750 / 5)),
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
        average_trade_pct=None,
        average_trade_margin_pct=None,
    )


def test_trade_stats_without_losses():
    stats = metrics.trade_stats([trade(10, 0, 1), trade(30, 2, 3)], TEN_BARS)

    assert (stats.win_rate_pct, stats.average_win) == (100, 20)
    assert stats.profit_factor is None
    assert stats.average_loss is None


# Daily returns of +1%, -1%, +3%, 0% and +1%: their mean is 0.8%, and their squared deviations
# from it sum to 0.00088, so the sample standard deviation is sqrt(0.00088 / 4).
DAILY = curve(list(100 * np.cumprod([1, 1.01, 0.99, 1.03, 1.0, 1.01])))
DAILY_SHARPE = 0.008 / math.sqrt(0.00088 / 4)
# Only the -1% day is downside: sqrt(0.01^2 / 5), over all five days.
DAILY_SORTINO = 0.008 / math.sqrt(0.0001 / 5)


def test_sharpe_ratio_by_hand():
    assert metrics.sharpe_ratio(DAILY) == pytest.approx(DAILY_SHARPE * math.sqrt(365))


def test_sortino_ratio_by_hand():
    assert metrics.sortino_ratio(DAILY) == pytest.approx(DAILY_SORTINO * math.sqrt(365))


def test_ratios_for_stock_exchange_days():
    assert metrics.sharpe_ratio(DAILY, 252) == pytest.approx(DAILY_SHARPE * math.sqrt(252))
    assert metrics.sortino_ratio(DAILY, 252) == pytest.approx(DAILY_SORTINO * math.sqrt(252))


def test_ratios_use_the_daily_closes_of_intraday_equity():
    # The same six days as hourly equity that wanders within each day.
    closes = np.repeat(DAILY.to_numpy(), 24)
    wander = np.random.default_rng(3).normal(0, 1, len(closes))
    wander[23::24] = 0  # each day's last hour is its close
    hourly = curve(list(closes + wander), freq="h")

    assert metrics.sharpe_ratio(hourly) == pytest.approx(DAILY_SHARPE * math.sqrt(365))
    assert metrics.sortino_ratio(hourly) == pytest.approx(DAILY_SORTINO * math.sqrt(365))


def test_ratios_need_two_daily_returns():
    within_a_day = curve([100, 120, 90, 130], freq="h")

    assert metrics.sharpe_ratio(within_a_day) is None
    assert metrics.sortino_ratio(within_a_day) is None


def test_ratios_of_flat_equity_are_undefined():
    flat = curve([100] * 10)

    assert metrics.sharpe_ratio(flat) is None
    assert metrics.sortino_ratio(flat) is None


def test_sortino_ratio_without_a_losing_day_is_undefined():
    rising = curve([100, 101, 103, 106])

    assert metrics.sharpe_ratio(rising) is not None
    assert metrics.sortino_ratio(rising) is None


def test_summarize_collects_every_metric():
    # Ten days of hourly bars, so that the daily ratios are defined.
    bars = random_bars(240)
    bars.index = pd.date_range("2026-01-01", periods=240, freq="h", tz="UTC")
    rng = np.random.default_rng(5)
    result = simulate(bars, rng.random(240) < 0.1, rng.random(240) < 0.1, BacktestConfig(10_000))

    summary = metrics.summarize(result, periods_per_year=252)

    equity = result.equity
    assert summary == metrics.Metrics(
        total_return_pct=metrics.total_return_pct(equity),
        cagr_pct=metrics.cagr_pct(equity),
        max_drawdown_pct=metrics.max_drawdown_pct(equity),
        sharpe_ratio=metrics.sharpe_ratio(equity, 252),
        sortino_ratio=metrics.sortino_ratio(equity, 252),
        **asdict(metrics.trade_stats(result.trades, equity.index)),
    )
    assert summary.num_trades > 5
    assert None not in (summary.cagr_pct, summary.sharpe_ratio, summary.sortino_ratio)


def daily(rows: list[tuple[float, float]]) -> pd.DataFrame:
    """Daily bars from (open, close) rows."""
    opens, closes = zip(*rows, strict=True)
    bars = pd.DataFrame({"open": opens, "close": closes}, dtype=float)
    bars.index = pd.date_range("2026-01-01", periods=len(rows), freq="D", tz="UTC")
    return bars


def test_buy_and_hold_by_hand():
    # 100 units bought at the first open of 100, marked at each close: up to 11,000, then down
    # to 9,900, 10% below that peak.
    bars = daily([(100, 105), (105, 110), (110, 99)])

    benchmark = metrics.buy_and_hold(bars, BacktestConfig(10_000))

    assert benchmark.equity.tolist() == [10_500, 11_000, 9_900]
    assert benchmark.return_pct == pytest.approx(-1)
    assert benchmark.max_drawdown_pct == pytest.approx(10)
    assert benchmark.cagr_pct == pytest.approx(((0.99 ** (365.25 / 2)) - 1) * 100)


def test_buy_and_hold_pays_the_backtests_costs():
    bars = daily([(100, 105), (105, 110)])
    config = BacktestConfig(10_000, fee_pct=0.1, slippage_pct=0.05)

    benchmark = metrics.buy_and_hold(bars, config)

    # The capital pays for the notional and its fee; the sale pays slippage and a fee too.
    size = 10_000 / 1.001 / (100 * 1.0005)
    assert benchmark.equity.iloc[0] == pytest.approx(size * 105)
    assert benchmark.equity.iloc[-1] == pytest.approx(size * 110 * 0.9995 * 0.999)


def test_buy_and_hold_counts_from_the_capital():
    # Down from the start: the drawdown counts from the capital, not from the first close.
    benchmark = metrics.buy_and_hold(daily([(100, 90), (90, 95)]), BacktestConfig(10_000))

    assert benchmark.max_drawdown_pct == pytest.approx(10)
    assert benchmark.return_pct == pytest.approx(-5)


def test_summarize_includes_buy_and_hold():
    bars = random_bars(240)
    bars.index = pd.date_range("2026-01-01", periods=240, freq="h", tz="UTC")
    result = simulate(bars, np.zeros(240, dtype=bool), None, BacktestConfig(10_000))
    benchmark = metrics.buy_and_hold(bars, BacktestConfig(10_000))

    summary = metrics.summarize(result, benchmark=benchmark)

    assert (
        summary.buy_and_hold_return_pct,
        summary.buy_and_hold_cagr_pct,
        summary.buy_and_hold_max_drawdown_pct,
    ) == (benchmark.return_pct, benchmark.cagr_pct, benchmark.max_drawdown_pct)
    # Without it, as for runs made before it was measured, the fields are empty.
    assert metrics.summarize(result).buy_and_hold_return_pct is None


def test_metrics_stored_before_buy_and_hold_still_read():
    stored = asdict(
        metrics.summarize(
            simulate(random_bars(10), np.zeros(10, bool), None, BacktestConfig(10_000))
        )
    )
    for field in (
        "buy_and_hold_return_pct",
        "buy_and_hold_cagr_pct",
        "buy_and_hold_max_drawdown_pct",
    ):
        del stored[field]

    assert TypeAdapter(metrics.Metrics).validate_python(stored).buy_and_hold_return_pct is None


def trade_between(entry: pd.Timestamp, exit_: pd.Timestamp, pnl: float) -> SimulatedTrade:
    return SimulatedTrade(
        direction=Direction.LONG,
        entry_time=entry,
        entry_price=100,
        exit_time=exit_,
        exit_price=100 + pnl,
        size=1,
        entry_fee=0,
        exit_fee=0,
        slippage=0,
        pnl=pnl,
        pnl_pct=pnl,
        exit_reason=ExitReason.SIGNAL,
    )


def test_split_summaries_by_hand():
    bars = daily([(100, 100), (100, 110), (110, 105), (105, 120), (120, 90), (90, 99)])
    days = bars.index
    equity = pd.Series([100.0, 110, 105, 120, 90, 99], index=days)
    # One trade crosses the split (it counts where it was entered), one is after it.
    trades = [trade_between(days[1], days[4], -10), trade_between(days[4], days[5], 9)]

    split = metrics.split_summaries(
        BacktestResult(trades, equity), bars, BacktestConfig(100), days[3]
    )

    before, after = split.in_sample, split.out_of_sample
    assert (before.total_return_pct, before.max_drawdown_pct) == (
        pytest.approx(5),
        pytest.approx(100 * 5 / 110),
    )
    # From the last equity before the split, 105: down to 99, and 25% below the peak of 120.
    assert after.total_return_pct == pytest.approx((99 / 105 - 1) * 100)
    assert after.max_drawdown_pct == pytest.approx(25)
    assert (before.num_trades, after.num_trades) == (1, 1)
    # The first trade holds two of the three bars before the split; the second, two of the
    # three after it.
    assert before.exposure_pct == pytest.approx(200 / 3)
    assert after.exposure_pct == pytest.approx(200 / 3)
    # Each side has its own buy and hold: 100 -> 105, then 105 -> 99.
    assert before.buy_and_hold_return_pct == pytest.approx(5)
    assert after.buy_and_hold_return_pct == pytest.approx((99 / 105 - 1) * 100)


@pytest.mark.parametrize("day", [0, 6], ids=["at the first bar", "after the last bar"])
def test_a_split_needs_bars_on_both_sides(day):
    bars = daily([(100, 100), (100, 110), (110, 105), (105, 120), (120, 90), (90, 99)])
    equity = pd.Series(100.0, index=bars.index)
    split_at = bars.index[0] + pd.Timedelta(days=day)

    with pytest.raises(ValueError, match="bars on both sides"):
        metrics.split_summaries(BacktestResult([], equity), bars, BacktestConfig(100), split_at)


def with_returns(*returns: float) -> list[SimulatedTrade]:
    return [trade(pnl, bar, bar) for bar, pnl in enumerate(returns)]


def test_the_average_trade_and_its_95_percent_range():
    stats = metrics.trade_stats(with_returns(2, -1, 4, 3), TEN_BARS)

    # A mean of 2; a sample standard deviation of sqrt(14 / 3); 1.96 standard errors.
    assert stats.average_trade_pct == pytest.approx(2)
    assert stats.average_trade_margin_pct == pytest.approx(1.96 * math.sqrt(14 / 3) / 2)


@pytest.mark.parametrize(("returns", "margin"), [((), None), ((5,), None), ((5, 5), 0)])
def test_the_range_needs_two_trades(returns, margin):
    stats = metrics.trade_stats(with_returns(*returns), TEN_BARS)

    assert stats.average_trade_margin_pct == margin
    assert stats.average_trade_pct == (returns[0] if returns else None)
