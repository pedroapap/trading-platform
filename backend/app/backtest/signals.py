"""Turning a strategy's rules into per-bar values.

Bars are a float DataFrame (`open/high/low/close/volume`) in time order. Every array here is
aligned with them, and element `t` depends on bars `0..t` only.
"""

import numpy as np
import pandas as pd

from app.backtest import indicators, patterns
from app.backtest.orders import Entry, Level, Orders
from app.strategies.definition import PriceEntry, StrategyDefinition
from app.strategies.rules import (
    AllOf,
    AnyOf,
    Arithmetic,
    Atr,
    Bbands,
    Condition,
    Ema,
    EqualHighs,
    EqualLows,
    Happened,
    Highest,
    Indicator,
    Lowest,
    Macd,
    Node,
    Not,
    Operand,
    Price,
    Rsi,
    Sma,
    SwingHigh,
    SwingLow,
    Value,
)


class OperandResolver:
    """Turns operands into float arrays, computing each indicator once per set of bars."""

    def __init__(self, bars: pd.DataFrame) -> None:
        self._bars = bars
        self._indicators: dict[tuple, pd.Series | pd.DataFrame] = {}
        self._patterns: dict[EqualLows | EqualHighs, np.ndarray] = {}

    def resolve(self, operand: Operand) -> np.ndarray:
        if isinstance(operand, Value):
            return np.full(len(self._bars), operand.value)
        if isinstance(operand, Arithmetic):
            left, right = (self.resolve(each) for each in operand.operands)
            return _ARITHMETIC[operand.key](left, right)
        return _shifted(self._current(operand), operand.bars_ago)

    def detect(self, pattern: EqualLows | EqualHighs) -> np.ndarray:
        """Where the pattern is confirmed, as a boolean array."""
        if pattern not in self._patterns:
            find = patterns.equal_lows if isinstance(pattern, EqualLows) else patterns.equal_highs
            self._patterns[pattern] = find(
                self._bars[pattern.source],
                pattern.strength,
                pattern.times,
                pattern.within,
                pattern.tolerance_pct,
            )
        return self._patterns[pattern]

    def _current(self, operand: Price | Indicator) -> np.ndarray:
        """The operand's values as of each bar, before any `bars_ago` shift."""
        if isinstance(operand, Price):
            return self._bars[operand.price].to_numpy(dtype=float)
        # MACD and Bollinger Bands compute all of their lines at once, so the key leaves out
        # which line is wanted; every shift of an indicator shares its computation too.
        key = tuple(operand.model_dump(exclude={"output", "bars_ago"}).items())
        if key not in self._indicators:
            self._indicators[key] = _compute(operand, self._bars)
        computed = self._indicators[key]
        if isinstance(computed, pd.DataFrame):
            computed = computed[operand.output]
        return computed.to_numpy(dtype=float)


def evaluate(node: Node, resolver: OperandResolver) -> np.ndarray:
    """Whether the rule holds on each bar, as a boolean array. A comparison with a missing
    value (an indicator still warming up) is false, and so is a `not` around it."""
    return _evaluate(node, resolver)[0]


def _evaluate(node: Node, resolver: OperandResolver) -> tuple[np.ndarray, np.ndarray]:
    """Whether the rule holds on each bar, and whether every value it uses is known there."""
    match node:
        case Condition(left=left, op=op, right=right):
            left_values, right_values = resolver.resolve(left), resolver.resolve(right)
            known = ~np.isnan(left_values) & ~np.isnan(right_values)
            if op in ("crosses_above", "crosses_below"):
                known &= _previous(known)  # a cross compares with the previous bar too
            return _OPERATORS[op](left_values, right_values), known
        case AllOf(all=rules) | AnyOf(any=rules):
            results = [_evaluate(rule, resolver) for rule in rules]
            combine = np.logical_and if isinstance(node, AllOf) else np.logical_or
            holds = combine.reduce([holds for holds, _ in results])
            return holds, np.logical_and.reduce([known for _, known in results])
        case Not(rule=rule):
            holds, known = _evaluate(rule, resolver)
            return ~holds & known, known
        case Happened(happened=rule, within=within, times=times):
            holds, known = _evaluate(rule, resolver)
            return _runs_within(holds, within) >= times, _known_throughout(known, within)
        case EqualLows() | EqualHighs():
            # A pattern is either confirmed on a bar or not: there is nothing unknown in it.
            holds = resolver.detect(node)
            return holds, np.ones_like(holds)
    raise TypeError(f"not a rule: {node!r}")


def strategy_signals(
    definition: StrategyDefinition, bars: pd.DataFrame
) -> tuple[np.ndarray, np.ndarray | None]:
    """Entry and exit signals (None without an exit rule). Indicators that both use are
    computed once."""
    resolver = OperandResolver(bars)
    entries = evaluate(definition.entry, resolver)
    exits = None if definition.exit is None else evaluate(definition.exit, resolver)
    return entries, exits


def strategy_orders(definition: StrategyDefinition, bars: pd.DataFrame) -> Orders:
    """What the definition asks of the engine on `bars`."""
    resolver = OperandResolver(bars)
    entries = evaluate(definition.entry, resolver)
    exits = None if definition.exit is None else evaluate(definition.exit, resolver)
    take_profit = (
        Level(r=definition.take_profit_r)
        if definition.take_profit_r is not None
        else _level(definition.take_profit_pct, definition.take_profit_at, resolver)
    )
    order = definition.entry_order
    entry = (
        Entry(order.type, resolver.resolve(order.price), order.expires_after)
        if isinstance(order, PriceEntry)
        else Entry()
    )
    return Orders(
        direction=definition.direction,
        entries=entries,
        exits=exits,
        stop_loss=_level(definition.stop_loss_pct, definition.stop_loss_at, resolver),
        take_profit=take_profit,
        entry=entry,
    )


def _level(pct: float | None, at: Operand | None, resolver: OperandResolver) -> Level | None:
    if at is not None:
        return Level(at=resolver.resolve(at))
    return None if pct is None else Level(pct=pct)


def _compute(operand: Indicator, bars: pd.DataFrame) -> pd.Series | pd.DataFrame:
    match operand:
        case Atr(period=period):
            return indicators.atr(bars["high"], bars["low"], bars["close"], period)
        case Sma(period=period, source=source):
            return indicators.sma(bars[source], period)
        case Ema(period=period, source=source):
            return indicators.ema(bars[source], period)
        case Rsi(period=period, source=source):
            return indicators.rsi(bars[source], period)
        case Macd(fast=fast, slow=slow, signal=signal, source=source):
            return indicators.macd(bars[source], fast, slow, signal)
        case Bbands(period=period, std=std, source=source):
            return indicators.bbands(bars[source], period, std)
        case Lowest(period=period, source=source):
            return indicators.lowest(bars[source], period)
        case Highest(period=period, source=source):
            return indicators.highest(bars[source], period)
        case SwingLow(strength=strength, occurrence=occurrence, source=source):
            return indicators.swing_low(bars[source], strength, occurrence)
        case SwingHigh(strength=strength, occurrence=occurrence, source=source):
            return indicators.swing_high(bars[source], strength, occurrence)
        case _:
            raise TypeError(f"not an indicator: {operand!r}")


def _divide(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """`left / right`, unknown (NaN) where `right` is 0."""
    with np.errstate(divide="ignore", invalid="ignore"):
        quotient = left / right
    return np.where(np.isfinite(quotient), quotient, np.nan)


_ARITHMETIC = {
    "add": np.add,
    "subtract": np.subtract,
    "multiply": np.multiply,
    "divide": _divide,
}


def _shifted(values: np.ndarray, bars: int) -> np.ndarray:
    """Each bar's value from `bars` bars earlier; unknown (NaN) where there is none."""
    if bars == 0:
        return values
    shifted = np.full(len(values), np.nan)
    shifted[bars:] = values[: max(len(values) - bars, 0)]
    return shifted


def _runs_within(holds: np.ndarray, bars: int) -> np.ndarray:
    """On each bar, how many separate runs of true values the last `bars` bars (this one
    included) touch. A run that began before them counts once."""
    runs = _window_sum(holds & ~_previous(holds), bars)
    if bars < len(holds):
        # A run already under way on the window's first bar began before the window.
        runs[bars:] += holds[1 : len(holds) - bars + 1] & holds[: len(holds) - bars]
    return runs


def _known_throughout(known: np.ndarray, bars: int) -> np.ndarray:
    """Whether values are known on every one of the last `bars` bars (this one included);
    false while there are fewer bars than that."""
    throughout = _window_sum(~known, bars) == 0
    throughout[: bars - 1] = False
    return throughout


def _window_sum(flags: np.ndarray, bars: int) -> np.ndarray:
    """How many of the last `bars` flags (this one included) are set, on each bar."""
    total = np.cumsum(flags, dtype=int)
    earlier = np.zeros_like(total)
    earlier[bars:] = total[: max(len(total) - bars, 0)]
    return total - earlier


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
