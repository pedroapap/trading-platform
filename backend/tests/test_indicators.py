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


def naive_swings(values: list[float], strength: int, lower: bool) -> list[int]:
    """Bars beyond each of the `strength` bars before them, and at least as far as each of the
    `strength` bars after them."""
    beyond = (lambda a, b: a < b) if lower else (lambda a, b: a > b)
    at_least = (lambda a, b: a <= b) if lower else (lambda a, b: a >= b)
    return [
        c
        for c in range(strength, len(values) - strength)
        if all(beyond(values[c], values[c - j]) for j in range(1, strength + 1))
        and all(at_least(values[c], values[c + j]) for j in range(1, strength + 1))
    ]


def naive_swing(values: list[float], strength: int, occurrence: int, lower: bool):
    swings = naive_swings(values, strength, lower)
    price, since = [], []
    for t in range(len(values)):
        known = [c for c in swings if c + strength <= t]
        if len(known) > occurrence:
            c = known[-1 - occurrence]
            price.append(values[c])
            since.append(t - c)
        else:
            price.append(NAN)
            since.append(NAN)
    return {"price": price, "bars_since": since}


def test_swing_lows_by_hand():
    lows = pd.Series([5.0, 4, 3, 4, 5, 4, 3.5, 4, 5])

    latest = indicators.swing_low(lows, 2)
    previous = indicators.swing_low(lows, 2, occurrence=1)

    # The low of 3 is known on bar 4, two bars after it; the low of 3.5 on bar 8.
    assert_series(latest["price"], [NAN] * 4 + [3, 3, 3, 3, 3.5])
    assert_series(latest["bars_since"], [NAN] * 4 + [2, 3, 4, 5, 2])
    assert_series(previous["price"], [NAN] * 8 + [3])
    assert_series(previous["bars_since"], [NAN] * 8 + [6])


def test_swing_highs_by_hand():
    highs = pd.Series([1.0, 2, 3, 2, 1, 2, 2.5, 2, 1])

    latest = indicators.swing_high(highs, 2)

    assert_series(latest["price"], [NAN] * 4 + [3, 3, 3, 3, 2.5])
    assert_series(latest["bars_since"], [NAN] * 4 + [2, 3, 4, 5, 2])


def test_the_first_bar_of_a_flat_bottom_is_the_swing():
    swings = indicators.swing_low(pd.Series([5.0, 3, 3, 5, 6]), 1)

    assert_series(swings["price"], [NAN, NAN, 3, 3, 3])
    assert_series(swings["bars_since"], [NAN, NAN, 1, 2, 3])


@pytest.mark.parametrize(("strength", "occurrence"), [(1, 0), (3, 0), (3, 2), (10, 1)])
@pytest.mark.parametrize("lower", [True, False], ids=["lows", "highs"])
def test_swings_match_the_naive_formula(strength, occurrence, lower):
    # Rounded, so that equal neighbours (flat bottoms and tops) occur too.
    prices = random_walk().round()
    swing = indicators.swing_low if lower else indicators.swing_high

    computed = swing(prices, strength, occurrence)

    expected = naive_swing(prices.tolist(), strength, occurrence, lower)
    assert_series(computed["price"], expected["price"])
    assert_series(computed["bars_since"], expected["bars_since"])


@pytest.mark.parametrize("swing", [indicators.swing_low, indicators.swing_high])
def test_swings_are_only_known_once_confirmed(swing):
    # A swing needs later bars to be confirmed, so this is where look-ahead could creep in:
    # what is known on each bar must not change when later bars arrive.
    prices = random_walk(120).round()
    full = swing(prices, 3, 1)

    for t in range(len(prices)):
        early = swing(prices.iloc[: t + 1], 3, 1)
        pd.testing.assert_frame_equal(early, full.iloc[: t + 1])


def vwap_of(rows, day, in_session=None) -> pd.Series:
    """VWAP of (high, low, close, volume) rows on the given trading days."""
    high, low, close, volume = (
        pd.Series(column, dtype=float) for column in zip(*rows, strict=True)
    )
    session = np.ones(len(rows), dtype=bool) if in_session is None else np.array(in_session)
    return indicators.vwap(high, low, close, volume, np.array(day), session)


def test_vwap_by_hand():
    rows = [
        (11, 9, 10, 1),  # typical price 10: VWAP 10
        (13, 11, 12, 3),  # 12: (10 * 1 + 12 * 3) / 4 = 11.5
        (12, 10, 11, 0),  # no volume: still 11.5
        (21, 19, 20, 2),  # the next day starts again: 20
        (16, 14, 15, 2),  # (20 * 2 + 15 * 2) / 4 = 17.5
    ]

    assert_series(vwap_of(rows, [1, 1, 1, 2, 2]), [10, 11.5, 11.5, 20, 17.5])


def test_vwap_is_unknown_before_the_days_first_volume_and_outside_the_session():
    rows = [(11, 9, 10, 5), (13, 11, 12, 0), (16, 14, 15, 1), (31, 29, 30, 9), (21, 19, 20, 1)]

    # Bar 0 is the day before; bar 3 is outside the session and left out of the average.
    vwap = vwap_of(rows, [1, 2, 2, 2, 2], in_session=[True, True, True, False, True])

    assert_series(vwap, [10, NAN, 15, NAN, 17.5])


def naive_vwap(rows, day) -> list[float]:
    values, traded, volume = [], 0.0, 0.0
    for i, (high, low, close, size) in enumerate(rows):
        if i == 0 or day[i] != day[i - 1]:
            traded = volume = 0.0
        traded += (high + low + close) / 3 * size
        volume += size
        values.append(traded / volume if volume else NAN)
    return values


def test_vwap_matches_the_naive_formula():
    rng = np.random.default_rng(5)
    close = random_walk(500)
    high = close + rng.uniform(0, 1, 500)
    low = close - rng.uniform(0, 1, 500)
    volume = rng.uniform(0, 100, 500)
    day = np.repeat(np.arange(10), 50)
    rows = list(zip(high, low, close, volume, strict=True))

    assert_series(vwap_of(rows, day), naive_vwap(rows, day))


def day_of(rows, day, days_ago, in_session=None) -> pd.DataFrame:
    """The trading day of (open, high, low, close) rows on the given days."""
    columns = (pd.Series(column, dtype=float) for column in zip(*rows, strict=True))
    session = np.ones(len(rows), dtype=bool) if in_session is None else np.array(in_session)
    return indicators.trading_day(*columns, np.array(day), session, days_ago)


# fmt: off
TWO_DAYS = [
    # open, high, low, close
    (10, 12,  9, 11),  # day 1
    (11, 14, 10, 13),
    (13, 13,  8,  9),
    (20, 21, 19, 20),  # day 2
    (20, 25, 20, 24),
]
# fmt: on


def test_today_so_far_by_hand():
    today = day_of(TWO_DAYS, [1, 1, 1, 2, 2], days_ago=0)

    assert_series(today["open"], [10, 10, 10, 20, 20])
    assert_series(today["high"], [12, 14, 14, 21, 25])
    assert_series(today["low"], [9, 9, 8, 19, 19])
    assert_series(today["close"], [11, 13, 9, 20, 24])


def test_an_earlier_day_is_whole_and_known_all_day():
    yesterday = day_of(TWO_DAYS, [1, 1, 1, 2, 2], days_ago=1)

    assert yesterday.iloc[:3].isna().all().all()
    assert yesterday.iloc[3:].to_numpy().tolist() == [[10, 14, 8, 9]] * 2
    assert day_of(TWO_DAYS, [1, 1, 1, 2, 2], days_ago=2).isna().all().all()


def test_days_without_bars_in_the_session_dont_count():
    # Bar 2 is alone on day 2, outside the session: day 3's day before is day 1.
    rows = [(10, 12, 9, 11), (11, 14, 10, 13), (50, 60, 40, 55), (20, 21, 19, 20), (20, 25, 20, 24)]
    in_session = [True, True, False, True, True]

    today = day_of(rows, [1, 1, 2, 3, 3], days_ago=0, in_session=in_session)
    yesterday = day_of(rows, [1, 1, 2, 3, 3], days_ago=1, in_session=in_session)

    assert_series(today["high"], [12, 14, NAN, 21, 25])
    assert yesterday.iloc[2:].to_numpy().tolist() == [[10, 14, 9, 13]] * 3


def range_of(highs, lows, elapsed, *, minutes, width, day=None, in_session=None):
    """The opening range of bars starting `elapsed` minutes into their day, for a session that
    opens at 09:30 (570)."""
    count = len(highs)
    return indicators.opening_range(
        pd.Series(highs, dtype=float),
        pd.Series(lows, dtype=float),
        np.zeros(count, dtype=int) if day is None else np.array(day),
        np.array(elapsed),
        np.ones(count, dtype=bool) if in_session is None else np.array(in_session),
        start=570,
        minutes=minutes,
        width=width,
    )


def test_the_opening_range_is_known_once_its_last_bar_closes():
    # Five-minute bars from 09:30: the first 15 minutes are the 09:30, 09:35 and 09:40 bars.
    found = range_of(
        [101, 103, 102, 108, 104],
        [99, 100, 98, 101, 97],
        [570, 575, 580, 585, 590],
        minutes=15,
        width=5,
    )

    assert_series(found["high"], [NAN, NAN, 103, 103, 103])
    assert_series(found["low"], [NAN, NAN, 98, 98, 98])


def test_each_day_has_its_own_opening_range_and_none_outside_the_session():
    found = range_of(
        [101, 103, 107, 111, 112],
        [99, 100, 105, 109, 110],
        [570, 575, 570, 575, 960],
        minutes=10,
        width=5,
        day=[1, 1, 2, 2, 2],
        in_session=[True, True, True, True, False],
    )

    assert_series(found["high"], [NAN, 103, NAN, 111, NAN])


def test_bars_longer_than_the_range_use_the_first_bar():
    # Half-hour bars with a 15-minute range: the 09:30 bar covers it, known at its close.
    found = range_of([101, 103], [99, 100], [570, 600], minutes=15, width=30)

    assert_series(found["high"], [101, 101])
