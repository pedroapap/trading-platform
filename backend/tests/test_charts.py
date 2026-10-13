import numpy as np
import pandas as pd

from app.backtest.charts import downsample_equity


def curve(values) -> pd.Series:
    index = pd.date_range("2026-01-01", periods=len(values), freq="min", tz="UTC")
    return pd.Series(values, index=index, dtype=float)


def test_a_short_curve_is_kept_whole():
    equity = curve([100, 99, 101])

    assert downsample_equity(equity, max_points=3).equals(equity)


def test_a_long_curve_keeps_its_ends_and_extremes():
    equity = curve(10_000 + np.cumsum(np.random.default_rng(2).normal(0, 10, 50_000)))

    sampled = downsample_equity(equity, max_points=1_000)

    assert 900 < len(sampled) <= 1_000
    assert sampled.index.is_monotonic_increasing
    assert sampled.equals(equity.loc[sampled.index])  # real points, unchanged
    assert {equity.index[0], equity.index[-1], equity.idxmin(), equity.idxmax()} <= set(
        sampled.index
    )


def test_a_one_bar_crash_stays_visible():
    # Evenly spaced points would almost surely miss a single bar.
    values = np.full(100_000, 10_000.0)
    values[54_321] = 7_000
    equity = curve(values)

    sampled = downsample_equity(equity, max_points=500)

    assert sampled.min() == 7_000
