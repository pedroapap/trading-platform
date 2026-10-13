import pandas as pd
import pytest

from app.backtest import metrics


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
