"""Turning a strategy's rules into per-bar values.

Bars are a float DataFrame (`open/high/low/close/volume`) in time order. Every array here is
aligned with them, and element `t` depends on bars `0..t` only.
"""

import numpy as np
import pandas as pd

from app.backtest import indicators
from app.strategies.definition import StrategyDefinition
from app.strategies.rules import (
    AllOf,
    AnyOf,
    Bbands,
    Condition,
    Ema,
    Indicator,
    Macd,
    Operand,
    Price,
    Rsi,
    Sma,
    Value,
)


class OperandResolver:
    """Turns operands into float arrays, computing each indicator once per set of bars."""

    def __init__(self, bars: pd.DataFrame) -> None:
        self._bars = bars
        self._indicators: dict[tuple, pd.Series | pd.DataFrame] = {}

    def resolve(self, operand: Operand) -> np.ndarray:
        if isinstance(operand, Value):
            return np.full(len(self._bars), operand.value)
        return _shifted(self._current(operand), operand.bars_ago)

    def _current(self, operand: Price | Indicator) -> np.ndarray:
        """The operand's values as of each bar, before any `bars_ago` shift."""
        if isinstance(operand, Price):
            return self._bars[operand.price].to_numpy(dtype=float)
        # MACD and Bollinger Bands compute all of their lines at once, so the key leaves out
        # which line is wanted; every shift of an indicator shares its computation too.
        key = tuple(operand.model_dump(exclude={"output", "bars_ago"}).items())
        if key not in self._indicators:
            self._indicators[key] = _compute(operand, self._bars[operand.source])
        computed = self._indicators[key]
        if isinstance(computed, pd.DataFrame):
            computed = computed[operand.output]
        return computed.to_numpy(dtype=float)


def evaluate(node: Condition | AllOf | AnyOf, resolver: OperandResolver) -> np.ndarray:
    """Whether the rule holds on each bar, as a boolean array. A comparison with a missing
    value (an indicator still warming up) is false."""
    if isinstance(node, AllOf):
        return np.logical_and.reduce([evaluate(child, resolver) for child in node.all])
    if isinstance(node, AnyOf):
        return np.logical_or.reduce([evaluate(child, resolver) for child in node.any])
    return _OPERATORS[node.op](resolver.resolve(node.left), resolver.resolve(node.right))


def strategy_signals(
    definition: StrategyDefinition, bars: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray | None]:
    """Entry and exit signals (None without an exit rule). Indicators that both use are
    computed once."""
    resolver = OperandResolver(bars)
    entries = evaluate(definition.entry, resolver)
    exits = None if definition.exit is None else evaluate(definition.exit, resolver)
    return entries, exits


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


def _shifted(values: np.ndarray, bars: int) -> np.ndarray:
    """Each bar's value from `bars` bars earlier; unknown (NaN) where there is none."""
    if bars == 0:
        return values
    shifted = np.full(len(values), np.nan)
    shifted[bars:] = values[: max(len(values) - bars, 0)]
    return shifted


def _crosses_above(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Above now, at or below on the previous bar (TradingView's `ta.crossover`)."""
    return (left > right) & _previous(left <= right)


def _crosses_below(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return (left < right) & _previous(left >= right)


def _previous(condition: np.ndarray) -> np.ndarray:
    """`condition` shifted one bar later; false on the first bar."""
    shifted = np.zeros_like(condition)
    shifted[1:] = condition[:-1]
    return shifted


_OPERATORS = {
    "<": np.less,
    "<=": np.less_equal,
    ">": np.greater,
    ">=": np.greater_equal,
    "crosses_above": _crosses_above,
    "crosses_below": _crosses_below,
}
