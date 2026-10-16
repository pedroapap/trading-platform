"""Technical indicators on price series.

Conventions match TradingView and TA-Lib, so values agree with common charts. Every function
takes a float Series and returns floats aligned with it: a Series, or for indicators with
several lines a DataFrame whose columns are the rule language's `output` names. Values are NaN
during the warm-up, and only NaN when the input is too short to warm up.
"""

import numpy as np
import pandas as pd


def sma(values: pd.Series, period: int) -> pd.Series:
    """Simple moving average; the first value is at index `period - 1`."""
    return values.rolling(period, min_periods=period).mean()


def ema(values: pd.Series, period: int) -> pd.Series:
    """Exponential moving average (alpha = 2 / (period + 1)), started from the SMA of the
    first `period` valid values. Leading NaNs are skipped, so an EMA of an indicator that
    has its own warm-up (e.g. MACD's signal line) works too."""
    return _smooth(values, period, alpha=2 / (period + 1))


def rsi(values: pd.Series, period: int) -> pd.Series:
    """Relative strength index with Wilder's smoothing (alpha = 1 / period), started from the
    mean gain and loss of the first `period` changes; the first value is at index `period`.

    100 when there are gains but no losses. 50 when the price has not moved at all, where
    TradingView says 100 and TA-Lib 0: neutral keeps flat data from looking overbought or
    oversold."""
    change = values.diff()
    gain = _smooth(change.clip(lower=0), period, alpha=1 / period)
    loss = _smooth((-change).clip(lower=0), period, alpha=1 / period)
    strength = 100 * gain / (gain + loss)
    return strength.mask((gain == 0) & (loss == 0), 50.0)


def macd(values: pd.Series, fast: int, slow: int, signal: int) -> pd.DataFrame:
    """MACD `line` (EMA(fast) - EMA(slow)), its `signal` line (an EMA of the line) and the
    `histogram` (line - signal). The line starts at index `slow - 1`; the signal and histogram
    at `slow + signal - 2`."""
    line = ema(values, fast) - ema(values, slow)
    signal_line = ema(line, signal)
    return pd.DataFrame({"line": line, "signal": signal_line, "histogram": line - signal_line})


def bbands(values: pd.Series, period: int, std: float) -> pd.DataFrame:
    """Bollinger Bands: the `middle` SMA, with `upper` and `lower` bands `std` population
    standard deviations (ddof 0, as TradingView and TA-Lib use) above and below it."""
    middle = sma(values, period)
    width = std * values.rolling(period, min_periods=period).std(ddof=0)
    return pd.DataFrame({"upper": middle + width, "middle": middle, "lower": middle - width})


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Average true range with Wilder's smoothing, as TradingView's `ta.atr`. A bar's true range
    is the largest of high - low, |high - previous close| and |low - previous close| (just
    high - low on the first bar); it is smoothed like RSI. The first value is at index
    `period - 1`."""
    previous = close.shift(1)
    ranges = pd.concat([high - low, (high - previous).abs(), (low - previous).abs()], axis=1)
    return _smooth(ranges.max(axis=1), period, alpha=1 / period)


def lowest(values: pd.Series, period: int) -> pd.Series:
    """The lowest value of the last `period` bars, this one included (TradingView's
    `ta.lowest`); the first value is at index `period - 1`."""
    return values.rolling(period, min_periods=period).min()


def highest(values: pd.Series, period: int) -> pd.Series:
    """The highest value of the last `period` bars, this one included (`ta.highest`)."""
    return values.rolling(period, min_periods=period).max()


def vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    day: np.ndarray,
    in_session: np.ndarray,
) -> pd.Series:
    """The volume-weighted average of each bar's typical price, (high + low + close) / 3, over
    its trading day `day` so far, counting bars `in_session` only. Unknown outside the session,
    and on a day's bars before any volume."""
    weight = volume.where(in_session, 0.0)
    traded = ((high + low + close) / 3 * weight).groupby(day).cumsum()
    so_far = weight.groupby(day).cumsum()
    return (traded / so_far.where(so_far > 0)).where(in_session)


def trading_day(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    day: np.ndarray,
    in_session: np.ndarray,
    days_ago: int,
) -> pd.DataFrame:
    """Each bar's trading day `day` as `open/high/low/close` columns, from bars `in_session`.
    With `days_ago` 0, today so far: the open of its first bar, its high and low until this
    bar, and this bar's close; unknown outside the session. Otherwise, the whole of the trading
    day that many days before (days without bars in the session don't count), on every bar of
    the day."""
    prices = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close})
    if days_ago == 0:
        session = prices.copy()
        session.loc[~in_session] = np.nan
        by_day = session.groupby(day)
        today = pd.DataFrame(
            {
                "open": by_day["open"].transform("first"),
                "high": by_day["high"].cummax(),
                "low": by_day["low"].cummin(),
                "close": session["close"],
            }
        )
        today.loc[~in_session] = np.nan
        return today
    whole = (
        prices[in_session]
        .groupby(day[in_session])
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
        )
    )
    # A bar's own day sits at its position in `whole`, or would if it had bars in the session.
    earlier = np.searchsorted(whole.index.to_numpy(), day) - days_ago
    known = earlier >= 0
    values = np.full((len(day), 4), np.nan)
    values[known] = whole.to_numpy()[earlier[known]]
    return pd.DataFrame(values, index=prices.index, columns=whole.columns)


def opening_range(
    high: pd.Series,
    low: pd.Series,
    day: np.ndarray,
    elapsed: np.ndarray,
    in_session: np.ndarray,
    start: int,
    minutes: int,
    width: int,
) -> pd.DataFrame:
    """The `high` and `low` of each trading day's bars in the session that start in its first
    `minutes` after `start` (minutes into the day; bars start at `elapsed` and last `width`).
    Known from the bar whose end reaches the range's end, when all of them have closed; unknown
    before it and outside the session."""
    in_range = in_session & (elapsed >= start) & (elapsed < start + minutes)
    by_day = pd.DataFrame({"high": high.where(in_range), "low": low.where(in_range)}).groupby(day)
    whole = pd.DataFrame(
        {"high": by_day["high"].transform("max"), "low": by_day["low"].transform("min")}
    )
    whole.loc[~(in_session & (elapsed + width >= start + minutes))] = np.nan
    return whole


def swing_low(values: pd.Series, strength: int, occurrence: int = 0) -> pd.DataFrame:
    """The swing lows known on each bar. A swing low is a bar lower than each of the `strength`
    bars before it and no higher than each of the `strength` bars after it, so the first bar of
    a flat bottom counts. It is only known once those later bars have closed, `strength` bars
    after it, as TradingView's `ta.pivotlow(source, strength, strength)`.

    Columns, for the `occurrence`-th most recent known swing low (0 is the latest): its `price`,
    and `bars_since` it, counted from the swing bar itself. NaN until there is one."""
    return _swings(-values, strength, occurrence, values)


def swing_high(values: pd.Series, strength: int, occurrence: int = 0) -> pd.DataFrame:
    """The swing highs known on each bar: bars higher than each of the `strength` bars before
    them and no lower than each of the `strength` bars after them (see `swing_low`)."""
    return _swings(values, strength, occurrence, values)


def swing_peaks(peaks: pd.Series, strength: int) -> np.ndarray:
    """The positions of the bars higher than each of the `strength` bars before them and no
    lower than each of the `strength` bars after them, in order. (Pass negated values to find
    swing lows.)"""
    before = peaks.shift(1).rolling(strength, min_periods=strength).max()
    after = peaks.rolling(strength, min_periods=strength).max().shift(-strength)
    return np.flatnonzero((peaks > before) & (peaks >= after))


def _swings(peaks: pd.Series, strength: int, occurrence: int, values: pd.Series) -> pd.DataFrame:
    """Swing highs of `peaks` (the values, or their negatives for lows), reported with
    `values`."""
    swing_bars = swing_peaks(peaks, strength)
    bars = np.arange(len(values))
    # On each bar, the number of swings known so far, then which of them is wanted.
    known = np.searchsorted(swing_bars + strength, bars, side="right")
    which = known - 1 - occurrence
    found = which >= 0
    swing_bar = swing_bars[which[found]]
    price = np.full(len(values), np.nan)
    since = np.full(len(values), np.nan)
    price[found] = values.to_numpy(dtype=float)[swing_bar]
    since[found] = bars[found] - swing_bar
    return pd.DataFrame({"price": price, "bars_since": since}, index=values.index)


def _smooth(values: pd.Series, period: int, alpha: float) -> pd.Series:
    """`s[t] = alpha * x[t] + (1 - alpha) * s[t-1]`, seeded with the SMA of the first `period`
    valid values (leading NaNs are skipped)."""
    raw = values.to_numpy(dtype=float)
    valid = np.flatnonzero(~np.isnan(raw))
    if len(valid) == 0 or len(raw) - valid[0] < period:
        return pd.Series(np.nan, index=values.index)
    seed_at = valid[0] + period - 1
    seeded = raw.copy()
    seeded[:seed_at] = np.nan
    seeded[seed_at] = raw[valid[0] : seed_at + 1].mean()
    smoothed = pd.Series(seeded, index=values.index)
    return smoothed.ewm(alpha=alpha, adjust=False).mean()
