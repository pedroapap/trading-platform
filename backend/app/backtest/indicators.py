"""Technical indicators on price series.

Conventions match TradingView and TA-Lib, so values agree with common charts. Every function
takes a float Series and returns a float Series aligned with it: NaN during the warm-up, and
only NaN when the input is too short to warm up.
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
