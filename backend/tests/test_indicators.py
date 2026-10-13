"""Indicators are checked against hand-computed cases and against deliberately naive loop
implementations of the textbook formulas (the `naive_*` helpers below)."""

import math

import numpy as np
import pandas as pd
import pytest

from app.backtest import indicators

NAN = math.nan


def random_walk(length: int = 300, seed: int = 7) -> pd.Series:
    steps = np.random.default_rng(seed).normal(0, 1, length)
    return pd.Series(100 + np.cumsum(steps))


def assert_series(actual: pd.Series, expected: list[float]) -> None:
    np.testing.assert_allclose(actual.to_numpy(), expected, rtol=1e-12, equal_nan=True)


def naive_sma(values: list[float], period: int) -> list[float]:
    return [
        NAN if i < period - 1 else sum(values[i - period + 1 : i + 1]) / period
        for i in range(len(values))
    ]


def test_sma_by_hand():
    assert_series(indicators.sma(pd.Series([1.0, 2, 3, 4, 5]), 3), [NAN, NAN, 2, 3, 4])


@pytest.mark.parametrize("period", [1, 5, 50])
def test_sma_matches_the_naive_formula(period):
    prices = random_walk()

    assert_series(indicators.sma(prices, period), naive_sma(prices.tolist(), period))


def test_sma_of_a_short_series_is_all_missing():
    assert indicators.sma(pd.Series([1.0, 2.0]), 3).isna().all()


def naive_ema(values: list[float], period: int) -> list[float]:
    alpha = 2 / (period + 1)
    start = next(i for i, v in enumerate(values) if not math.isnan(v))
    seed_at = start + period - 1
    result = [NAN] * len(values)
    result[seed_at] = sum(values[start : seed_at + 1]) / period
    for i in range(seed_at + 1, len(values)):
        result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]
    return result


def test_ema_by_hand():
    # alpha = 0.5; seed = mean(1, 2, 3) = 2; then 0.5*4 + 0.5*2 = 3, and so on
    assert_series(indicators.ema(pd.Series([1.0, 2, 3, 4, 5, 6]), 3), [NAN, NAN, 2, 3, 4, 5])


@pytest.mark.parametrize("period", [1, 12, 26])
def test_ema_matches_the_naive_formula(period):
    prices = random_walk()

    assert_series(indicators.ema(prices, period), naive_ema(prices.tolist(), period))


def test_ema_is_seeded_with_the_sma():
    prices = random_walk()

    assert indicators.ema(prices, 20)[19] == pytest.approx(indicators.sma(prices, 20)[19])


def test_ema_skips_leading_missing_values():
    values = pd.Series([NAN, NAN, 1.0, 2, 3, 4])

    assert_series(indicators.ema(values, 3), [NAN, NAN, NAN, NAN, 2, 3])


@pytest.mark.parametrize("values", [[1.0, 2.0], [NAN, NAN, NAN], []])
def test_ema_of_too_little_data_is_all_missing(values):
    assert indicators.ema(pd.Series(values, dtype=float), 3).isna().all()
