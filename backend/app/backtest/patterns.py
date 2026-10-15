"""Chart patterns built from swing points. Each is true on the bar where it is confirmed, so
like everything a rule uses, it depends on that bar and earlier ones only."""

import numpy as np
import pandas as pd

from app.backtest.indicators import swing_peaks


def equal_lows(
    values: pd.Series, strength: int, times: int, within: int, tolerance_pct: float
) -> np.ndarray:
    """Whether, on each bar, the swing low confirmed there (see `indicators.swing_low`) is the
    last of `times` swing lows at one level: `times - 1` earlier swing lows, the most recent
    ones within `tolerance_pct` of it, that began fewer than `within` bars before it. And the
    line held: price never went below the lowest of them by more than `tolerance_pct` in
    between. With `times` 2 this is a double bottom."""
    return _equal_swings(values, strength, times, within, tolerance_pct, lows=True)


def equal_highs(
    values: pd.Series, strength: int, times: int, within: int, tolerance_pct: float
) -> np.ndarray:
    """Swing highs at one level, as `equal_lows` (a double top with `times` 2)."""
    return _equal_swings(values, strength, times, within, tolerance_pct, lows=False)


def _equal_swings(
    values: pd.Series, strength: int, times: int, within: int, tolerance_pct: float, lows: bool
) -> np.ndarray:
    prices = values.to_numpy(dtype=float)
    fires = np.zeros(len(prices), dtype=bool)
    swings = swing_peaks(-values if lows else values, strength)
    if len(swings) < times:
        return fires
    tolerance = tolerance_pct / 100
    level = prices[swings]
    # The most extreme price from each swing up to (not including) the next one: where the
    # line could have broken between them.
    extreme, beyond = (np.minimum, np.inf) if lows else (np.maximum, -np.inf)
    segment = extreme.reduceat(prices, swings)

    count = len(swings)
    found = np.zeros(count, dtype=int)  # earlier swings matched so far, most recent first
    line = level.copy()  # the most extreme of the swings matched so far
    span = np.full(count, beyond)  # the most extreme price since the earliest swing looked at
    settled = np.zeros(count, dtype=bool)
    # Walk back one swing at a time, for every swing at once.
    for lag in range(1, count):
        latest = np.arange(lag, count)
        earlier = latest - lag
        in_window = swings[latest] - swings[earlier] < within
        if not in_window.any():
            break
        span[latest] = extreme(span[latest], segment[earlier])
        close = np.abs(level[earlier] - level[latest]) <= tolerance * level[latest]
        match = in_window & close & ~settled[latest]
        found[latest] += match
        line[latest] = np.where(match, extreme(line[latest], level[earlier]), line[latest])
        complete = match & (found[latest] == times - 1)
        if lows:
            held = span[latest] >= line[latest] * (1 - tolerance)
        else:
            held = span[latest] <= line[latest] * (1 + tolerance)
        confirmed = swings[latest[complete & held]] + strength
        fires[confirmed[confirmed < len(prices)]] = True
        settled[latest[complete]] = True
    return fires
