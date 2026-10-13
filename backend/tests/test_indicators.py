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
