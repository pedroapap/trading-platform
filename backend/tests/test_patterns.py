"""Chart patterns are checked against planted cases and against a naive loop that follows
their definitions."""

import numpy as np
import pandas as pd
import pytest

from app.backtest import patterns

# Swing lows (strength 2) of 8 on bar 2 and 8.02 on bar 10, with a higher one of 9 between:
# a double bottom, confirmed on bar 12.
DOUBLE_BOTTOM = [10, 9, 8, 9, 10, 9.5, 9, 9.5, 10, 9, 8.02, 9, 10]


def fired(found: np.ndarray) -> list[int]:
    return np.flatnonzero(found).tolist()


def equal_lows(values: list[float], **overrides) -> list[int]:
    settings = {"strength": 2, "times": 2, "within": 10, "tolerance_pct": 0.5} | overrides
    return fired(patterns.equal_lows(pd.Series(values, dtype=float), **settings))


def test_a_double_bottom_fires_once_confirmed():
    assert equal_lows(DOUBLE_BOTTOM) == [12]


@pytest.mark.parametrize(
    ("overrides", "why"),
    [
        ({"within": 8}, "the second low is 8 bars after the first"),
        ({"tolerance_pct": 0.1}, "0.02 apart is more than 0.1% of 8.02"),
        ({"strength": 3}, "neither low has 3 bars on each side to confirm it"),
    ],
)
def test_lows_that_do_not_qualify_make_no_pattern(overrides, why):
    assert equal_lows(DOUBLE_BOTTOM, **overrides) == [], why


def test_a_broken_line_is_not_a_double_bottom():
    broken = DOUBLE_BOTTOM.copy()
    broken[6] = 7.5  # a lower low between the two

    assert equal_lows(broken) == []


def test_a_triple_bottom_needs_three_lows():
    triple = [10, 9, 8, 9, 10, 9, 8.01, 9, 10, 9, 8.02, 9, 10]

    assert equal_lows(triple, times=3) == [12]
    # Each pair of neighbours makes a double bottom.
    assert equal_lows(triple, times=2) == [8, 12]


def test_a_double_top_mirrors_it():
    highs = pd.Series([1, 2, 3, 2, 1, 2, 3.01, 2, 1], dtype=float)

    assert fired(patterns.equal_highs(highs, 2, 2, 10, 0.5)) == [8]


def naive_swings(values: list[float], strength: int, lows: bool) -> list[int]:
    beyond = (lambda a, b: a < b) if lows else (lambda a, b: a > b)
    level = (lambda a, b: a <= b) if lows else (lambda a, b: a >= b)
    return [
        c
        for c in range(strength, len(values) - strength)
        if all(beyond(values[c], values[c - j]) for j in range(1, strength + 1))
        and all(level(values[c], values[c + j]) for j in range(1, strength + 1))
    ]


def naive_equal_swings(
    values: list[float], strength: int, times: int, within: int, tolerance_pct: float, lows: bool
) -> list[int]:
    """The definition, one swing at a time: match the most recent earlier swings in the
    window, then check the line held from the first of them."""
    tolerance = tolerance_pct / 100
    swings = naive_swings(values, strength, lows)
    found = []
    for j, latest in enumerate(swings):
        matched = []
        for earlier in reversed(swings[:j]):
            if latest - earlier >= within:
                break
            if abs(values[earlier] - values[latest]) <= tolerance * values[latest]:
                matched.append(earlier)
                if len(matched) == times - 1:
                    break
        if len(matched) < times - 1:
            continue
        group = [values[i] for i in matched] + [values[latest]]
        between = values[min(matched) : latest + 1]
        if lows:
            held = min(between) >= min(group) * (1 - tolerance)
        else:
            held = max(between) <= max(group) * (1 + tolerance)
        if held and latest + strength < len(values):
            found.append(latest + strength)
    return found


def rounded_walk(length: int = 600, seed: int = 3) -> pd.Series:
    """A random walk rounded to whole numbers, so that many swings sit at the same level."""
    steps = np.random.default_rng(seed).normal(0, 1.5, length)
    return pd.Series(100 + np.cumsum(steps)).round()


@pytest.mark.parametrize(
    ("strength", "times", "within", "tolerance_pct"),
    [(1, 2, 20, 0.5), (2, 2, 50, 1.0), (3, 3, 100, 1.5), (1, 4, 200, 2.0)],
)
@pytest.mark.parametrize("lows", [True, False], ids=["lows", "highs"])
def test_patterns_match_the_naive_definition(strength, times, within, tolerance_pct, lows):
    prices = rounded_walk()
    find = patterns.equal_lows if lows else patterns.equal_highs

    found = fired(find(prices, strength, times, within, tolerance_pct))

    expected = naive_equal_swings(prices.tolist(), strength, times, within, tolerance_pct, lows)
    assert found == expected
    assert found, "the walk should hold some of these patterns"


@pytest.mark.parametrize("find", [patterns.equal_lows, patterns.equal_highs])
def test_patterns_never_look_ahead(find):
    prices = rounded_walk(150)
    full = find(prices, 2, 2, 30, 1.0)

    for t in range(len(prices)):
        np.testing.assert_array_equal(find(prices.iloc[: t + 1], 2, 2, 30, 1.0), full[: t + 1])
