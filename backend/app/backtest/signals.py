"""Turning a strategy's rules into per-bar values.

Bars are a float DataFrame (`open/high/low/close/volume`) in time order. Every array here is
aligned with them, and element `t` depends on bars `0..t` only.
"""

import numpy as np
import pandas as pd

from app.backtest import indicators
from app.strategies.rules import Bbands, Ema, Macd, Operand, Price, Rsi, Sma, Value


class OperandResolver:
    """Turns operands into float arrays, computing each indicator once per set of bars."""

    def __init__(self, bars: pd.DataFrame) -> None:
        self._bars = bars
        self._indicators: dict[tuple, pd.Series | pd.DataFrame] = {}

    def resolve(self, operand: Operand) -> np.ndarray:
        if isinstance(operand, Value):
            return np.full(len(self._bars), operand.value)
        if isinstance(operand, Price):
            return self._bars[operand.price].to_numpy(dtype=float)
        # MACD and Bollinger Bands compute all of their lines at once, so the key leaves out
        # which line is wanted.
        key = tuple(operand.model_dump(exclude={"output"}).items())
        if key not in self._indicators:
            self._indicators[key] = _compute(operand, self._bars[operand.source])
        computed = self._indicators[key]
        if isinstance(computed, pd.DataFrame):
            computed = computed[operand.output]
        return computed.to_numpy(dtype=float)


def _compute(operand: Operand, values: pd.Series) -> pd.Series | pd.DataFrame:
    match operand:
        case Sma(period=period):
            return indicators.sma(values, period)
        case Ema(period=period):
            return indicators.ema(values, period)
        case Rsi(period=period):
            return indicators.rsi(values, period)
        case Macd(fast=fast, slow=slow, signal=signal):
            return indicators.macd(values, fast, slow, signal)
        case Bbands(period=period, std=std):
            return indicators.bbands(values, period, std)
        case _:
            raise TypeError(f"not an indicator: {operand!r}")
