"""Performance metrics of a backtest, from its equity curve and its trades."""

import math

import pandas as pd

YEAR = pd.Timedelta(days=365.25)


def total_return_pct(equity: pd.Series) -> float:
    """Change from the first to the last equity value, in percent."""
    return float((equity.iloc[-1] / equity.iloc[0] - 1) * 100)


def cagr_pct(equity: pd.Series) -> float | None:
    """Compound annual growth rate over the time the equity curve spans, in percent: -100
    once the equity is gone, None when the curve spans no time or annualizing a very short
    span overflows."""
    years = (equity.index[-1] - equity.index[0]) / YEAR
    if years <= 0:
        return None
    growth = equity.iloc[-1] / equity.iloc[0]
    if growth <= 0:
        return -100.0
    try:
        cagr = (float(growth) ** (1 / years) - 1) * 100
    except OverflowError:
        return None
    return cagr if math.isfinite(cagr) else None


def max_drawdown_pct(equity: pd.Series) -> float:
    """The largest fall from a running peak, as a percentage of that peak; 0 when equity
    never falls."""
    peaks = equity.cummax()
    return float(((peaks - equity) / peaks).max() * 100)
