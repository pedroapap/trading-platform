"""Indicators are checked against hand-computed cases and against deliberately naive loop
implementations of the textbook formulas (the `naive_*` helpers below)."""

import math
from itertools import pairwise

import numpy as np
import pandas as pd
import pytest

from app.backtest import indicators

NAN = math.nan


def random_walk(length: int = 300, seed: int = 7) -> pd.Series:
    steps = np.random.default_rng(seed).normal(0, 1, length)
    return pd.Series(100 + np.cumsum(steps))


def assert_series(actual: pd.Series, expected: list[float], atol: float = 0) -> None:
    np.testing.assert_allclose(actual.to_numpy(), expected, rtol=1e-12, atol=atol, equal_nan=True)


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


# StockCharts ChartSchool's RSI example (cs-rsi.xls): closes and the published RSI(14), 2 dp.
# fmt: off
STOCKCHARTS_CLOSES = [
    44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826,
    45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439,
    46.2122, 46.2521, 45.7137, 46.4515, 45.7835, 45.3548, 44.0288, 44.1783, 44.2181, 44.5672,
    43.4205, 42.6628, 43.1314,
]
STOCKCHARTS_RSI_14 = [
    70.53, 66.32, 66.55, 69.41, 66.36, 57.97, 62.93, 63.26, 56.06, 62.38,
    54.71, 50.42, 39.99, 41.46, 41.87, 45.46, 37.30, 33.08, 37.77,
]
# fmt: on


def naive_rsi(values: list[float], period: int) -> list[float]:
    changes = [b - a for a, b in pairwise(values)]
    gain = sum(max(change, 0) for change in changes[:period]) / period
    loss = sum(max(-change, 0) for change in changes[:period]) / period
    result = [NAN] * len(values)
    for i in range(period, len(values)):
        if i > period:
            gain = (gain * (period - 1) + max(changes[i - 1], 0)) / period
            loss = (loss * (period - 1) + max(-changes[i - 1], 0)) / period
        result[i] = 100 - 100 / (1 + gain / loss)
    return result


def test_rsi_matches_stockcharts():
    result = indicators.rsi(pd.Series(STOCKCHARTS_CLOSES), 14)

    assert result[:14].isna().all()
    np.testing.assert_allclose(result[14:], STOCKCHARTS_RSI_14, atol=0.005)


@pytest.mark.parametrize("period", [2, 14, 30])
def test_rsi_matches_the_naive_formula(period):
    prices = random_walk()

    assert_series(indicators.rsi(prices, period), naive_rsi(prices.tolist(), period))


@pytest.mark.parametrize("period", [2, 14])
def test_rsi_starts_at_index_period(period):
    assert indicators.rsi(random_walk(), period).first_valid_index() == period


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        ([5.0] * 20, 50),
        ([float(i) for i in range(20)], 100),
        ([float(i) for i in range(20, 0, -1)], 0),
    ],
    ids=["flat", "only-rising", "only-falling"],
)
def test_rsi_of_a_one_way_price(values, expected):
    result = indicators.rsi(pd.Series(values), 14)

    assert (result[14:] == expected).all()


@pytest.mark.parametrize("values", [[1.0] * 14, [1.0], []])
def test_rsi_of_a_short_series_is_all_missing(values):
    assert indicators.rsi(pd.Series(values, dtype=float), 14).isna().all()


def naive_macd(values: list[float], fast: int, slow: int, signal: int) -> dict[str, list[float]]:
    line = [a - b for a, b in zip(naive_ema(values, fast), naive_ema(values, slow), strict=True)]
    signal_line = naive_ema(line, signal)
    histogram = [a - b for a, b in zip(line, signal_line, strict=True)]
    return {"line": line, "signal": signal_line, "histogram": histogram}


@pytest.mark.parametrize(("fast", "slow", "signal"), [(12, 26, 9), (3, 10, 4)])
def test_macd_matches_the_naive_formula(fast, slow, signal):
    prices = random_walk()

    result = indicators.macd(prices, fast, slow, signal)

    expected = naive_macd(prices.tolist(), fast, slow, signal)
    assert list(result.columns) == ["line", "signal", "histogram"]
    for column in result.columns:
        # Differences of prices near 100 can be near zero, where a few ULPs of the prices are a
        # large relative error, so compare in price units.
        assert_series(result[column], expected[column], atol=1e-12)


def test_macd_warm_up():
    result = indicators.macd(random_walk(), 12, 26, 9)

    assert result["line"].first_valid_index() == 25
    assert result["signal"].first_valid_index() == 33
    assert result["histogram"].first_valid_index() == 33


def test_macd_keeps_the_index():
    prices = random_walk(50)
    prices.index = pd.date_range("2026-01-01", periods=50, freq="min", tz="UTC")

    assert indicators.macd(prices, 12, 26, 9).index.equals(prices.index)


@pytest.mark.parametrize("length", [25, 1, 0])
def test_macd_of_a_short_series_is_all_missing(length):
    result = indicators.macd(random_walk(length), 12, 26, 9)

    assert len(result) == length
    assert result.isna().all().all()


def test_macd_signal_waits_for_enough_line_values():
    result = indicators.macd(random_walk(33), 12, 26, 9)

    assert result["line"].notna().sum() == 8
    assert result[["signal", "histogram"]].isna().all().all()


def naive_bbands(values: list[float], period: int, std: float) -> dict[str, list[float]]:
    middle = naive_sma(values, period)
    width = [NAN] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        width[i] = std * math.sqrt(sum((v - middle[i]) ** 2 for v in window) / period)
    return {
        "upper": [m + w for m, w in zip(middle, width, strict=True)],
        "middle": middle,
        "lower": [m - w for m, w in zip(middle, width, strict=True)],
    }


def test_bbands_by_hand():
    # mean 5; squared deviations 9+1+1+1+0+0+4+16 = 32, so the population std is sqrt(32/8) = 2
    result = indicators.bbands(pd.Series([2.0, 4, 4, 4, 5, 5, 7, 9]), 8, 2)

    assert result.iloc[:7].isna().all().all()
    assert result.iloc[7].tolist() == [9, 5, 1]


@pytest.mark.parametrize(("period", "std"), [(2, 1.0), (20, 2.0), (50, 2.5)])
def test_bbands_match_the_naive_formula(period, std):
    prices = random_walk()

    result = indicators.bbands(prices, period, std)

    expected = naive_bbands(prices.tolist(), period, std)
    assert list(result.columns) == ["upper", "middle", "lower"]
    for column in result.columns:
        assert_series(result[column], expected[column])


def test_bbands_of_a_flat_price_collapse_onto_the_middle():
    result = indicators.bbands(pd.Series([5.0] * 10), 3, 2)

    assert (result.iloc[2:] == 5).all().all()


def test_bbands_keep_the_index():
    prices = random_walk(30)
    prices.index = pd.date_range("2026-01-01", periods=30, freq="min", tz="UTC")

    assert indicators.bbands(prices, 20, 2).index.equals(prices.index)


@pytest.mark.parametrize("length", [19, 1, 0])
def test_bbands_of_a_short_series_is_all_missing(length):
    result = indicators.bbands(random_walk(length), 20, 2)

    assert len(result) == length
    assert result.isna().all().all()


def random_bars(length: int = 300, seed: int = 11) -> pd.DataFrame:
    """Highs and lows around a random walk of closes, with gaps between bars."""
    rng = np.random.default_rng(seed)
    close = random_walk(length, seed)
    high = close + rng.uniform(0, 2, length)
    low = close - rng.uniform(0, 2, length)
    return pd.DataFrame({"high": high, "low": low, "close": close})


def naive_atr(high: list[float], low: list[float], close: list[float], period: int) -> list[float]:
    ranges = [high[0] - low[0]] + [
        max(h - lo, abs(h - c), abs(lo - c))
        for h, lo, c in zip(high[1:], low[1:], close[:-1], strict=True)
    ]
    result = [NAN] * len(ranges)
    if len(ranges) < period:
        return result
    average = sum(ranges[:period]) / period
    result[period - 1] = average
    for i in range(period, len(ranges)):
        average = (average * (period - 1) + ranges[i]) / period
        result[i] = average
    return result


def test_atr_by_hand():
    # True ranges 1, 2.5 (from the previous close), 4 (a gap up) and 3, smoothed over 2 bars.
    high = pd.Series([10.0, 12, 15, 14])
    low = pd.Series([9.0, 10, 13, 11])
    close = pd.Series([9.5, 11, 14, 12])

    assert_series(indicators.atr(high, low, close, 2), [NAN, 1.75, 2.875, 2.9375])


@pytest.mark.parametrize("period", [1, 14, 50])
def test_atr_matches_the_naive_formula(period):
    bars = random_bars()

    assert_series(
        indicators.atr(bars["high"], bars["low"], bars["close"], period),
        naive_atr(bars["high"].tolist(), bars["low"].tolist(), bars["close"].tolist(), period),
    )


def test_atr_of_a_short_series_is_all_missing():
    bars = random_bars(13)

    assert indicators.atr(bars["high"], bars["low"], bars["close"], 14).isna().all()


def naive_window(values: list[float], period: int, pick) -> list[float]:
    return [
        NAN if i < period - 1 else pick(values[i - period + 1 : i + 1]) for i in range(len(values))
    ]


def test_lowest_and_highest_by_hand():
    values = pd.Series([5.0, 3, 4, 1, 2])

    assert_series(indicators.lowest(values, 3), [NAN, NAN, 3, 1, 1])
    assert_series(indicators.highest(values, 3), [NAN, NAN, 5, 4, 4])


@pytest.mark.parametrize("period", [1, 20, 200])
def test_lowest_and_highest_match_the_naive_formula(period):
    prices = random_walk()

    assert_series(indicators.lowest(prices, period), naive_window(prices.tolist(), period, min))
    assert_series(indicators.highest(prices, period), naive_window(prices.tolist(), period, max))


def test_lowest_of_a_short_series_is_all_missing():
    assert indicators.lowest(pd.Series([1.0, 2.0]), 3).isna().all()
