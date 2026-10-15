import math

import numpy as np
import pandas as pd
import pytest
from pydantic import TypeAdapter

from app.backtest import indicators
from app.backtest.signals import OperandResolver, evaluate, strategy_signals
from app.strategies.definition import StrategyDefinition
from app.strategies.rules import Node, Operand
from tests.helpers import MINIMAL_DEFINITION, random_bars

NAN = math.nan

parse_operand = TypeAdapter(Operand).validate_python


def test_a_value_is_constant():
    bars = random_bars(10)

    resolved = OperandResolver(bars).resolve(parse_operand({"value": 30}))

    assert resolved.tolist() == [30.0] * 10


def test_a_price_is_its_bar_column():
    bars = random_bars()

    resolved = OperandResolver(bars).resolve(parse_operand({"price": "high"}))

    np.testing.assert_array_equal(resolved, bars["high"])


@pytest.mark.parametrize(
    ("operand", "direct"),
    [
        (
            {"indicator": "sma", "period": 20, "source": "volume"},
            lambda b: indicators.sma(b["volume"], 20),
        ),
        (
            {"indicator": "ema", "period": 10, "source": "open"},
            lambda b: indicators.ema(b["open"], 10),
        ),
        ({"indicator": "rsi"}, lambda b: indicators.rsi(b["close"], 14)),
        (
            {"indicator": "macd", "output": "signal"},
            lambda b: indicators.macd(b["close"], 12, 26, 9)["signal"],
        ),
        (
            {"indicator": "bbands", "std": 2.5, "output": "lower", "source": "low"},
            lambda b: indicators.bbands(b["low"], 20, 2.5)["lower"],
        ),
    ],
    ids=["sma", "ema", "rsi", "macd", "bbands"],
)
def test_an_indicator_is_computed_on_its_source(operand, direct):
    bars = random_bars()

    resolved = OperandResolver(bars).resolve(parse_operand(operand))

    np.testing.assert_array_equal(resolved, direct(bars))


def test_bars_ago_takes_the_value_that_many_bars_earlier():
    bars = random_bars(30)
    resolver = OperandResolver(bars)

    previous_low = resolver.resolve(parse_operand({"price": "low", "bars_ago": 1}))
    sma = resolver.resolve(parse_operand({"indicator": "sma", "period": 5}))
    earlier_sma = resolver.resolve(parse_operand({"indicator": "sma", "period": 5, "bars_ago": 3}))

    np.testing.assert_array_equal(previous_low, [NAN, *bars["low"].iloc[:-1]])
    np.testing.assert_array_equal(earlier_sma, [NAN] * 3 + sma[:-3].tolist())


def test_bars_ago_beyond_the_data_is_unknown():
    resolved = OperandResolver(random_bars(5)).resolve(
        parse_operand({"price": "close", "bars_ago": 9})
    )

    assert np.isnan(resolved).all()


@pytest.mark.parametrize(
    ("operation", "expected"),
    [("add", [5.0, 7.0]), ("subtract", [-3.0, -3.0]), ("multiply", [4.0, 10.0])],
)
def test_arithmetic_combines_two_operands(operation, expected):
    bars = pd.DataFrame({"open": [1.0, 2.0], "close": [4.0, 5.0]})
    data = {operation: [{"price": "open"}, {"price": "close"}]}

    assert OperandResolver(bars).resolve(parse_operand(data)).tolist() == expected


def test_dividing_by_zero_is_unknown():
    bars = pd.DataFrame({"open": [1.0, 0.0, -2.0], "close": [3.0, 3.0, 0.0]})

    quotient = OperandResolver(bars).resolve(
        parse_operand({"divide": [{"price": "close"}, {"price": "open"}]})
    )

    np.testing.assert_array_equal(quotient, [3.0, NAN, -0.0])


@pytest.fixture
def indicator_calls(monkeypatch) -> list[str]:
    """Calls to `indicators.rsi` and `indicators.macd` during the test, in order. (Not SMA or
    EMA: MACD and Bollinger Bands call those internally.)"""
    calls: list[str] = []

    def spy(name):
        original = getattr(indicators, name)

        def counted(*args):
            calls.append(name)
            return original(*args)

        return counted

    monkeypatch.setattr(indicators, "rsi", spy("rsi"))
    monkeypatch.setattr(indicators, "macd", spy("macd"))
    return calls


def test_each_indicator_is_computed_once(indicator_calls):
    resolver = OperandResolver(random_bars())

    for operand in [
        {"indicator": "rsi", "period": 14},
        {"indicator": "rsi"},  # equal to the first once defaults are filled in
        {"indicator": "rsi", "period": 7},
        {"indicator": "macd", "output": "line"},
        {"indicator": "macd", "output": "signal"},  # same MACD, another of its lines
        {"indicator": "rsi", "bars_ago": 3},  # the first RSI, shifted
        {"indicator": "macd", "output": "histogram", "bars_ago": 1},
    ]:
        resolver.resolve(parse_operand(operand))

    assert sorted(indicator_calls) == ["macd", "rsi", "rsi"]


parse_rule = TypeAdapter(Node).validate_python

CLOSE = {"price": "close"}
OPEN = {"price": "open"}
T, F = True, False


def holds(rule: dict, **columns: list[float]) -> list[bool]:
    bars = pd.DataFrame({name: np.array(values, dtype=float) for name, values in columns.items()})
    return evaluate(parse_rule(rule), OperandResolver(bars)).tolist()


@pytest.mark.parametrize(
    ("op", "expected"),
    [("<", [T, F, F]), ("<=", [T, T, F]), (">", [F, F, T]), (">=", [F, T, T])],
)
def test_comparison(op, expected):
    assert holds({"left": CLOSE, "op": op, "right": {"value": 2}}, close=[1, 2, 3]) == expected


@pytest.mark.parametrize("op", ["<", "<=", ">", ">="])
def test_a_comparison_with_a_missing_value_is_false(op):
    rule = {"left": OPEN, "op": op, "right": CLOSE}

    assert holds(rule, open=[NAN, 2, NAN], close=[2, NAN, NAN]) == [F, F, F]


def test_a_comparison_with_a_division_by_zero_is_false():
    rule = {"left": {"divide": [CLOSE, OPEN]}, "op": ">", "right": {"value": 0}}

    assert holds(rule, open=[1, 0], close=[3, 3]) == [T, F]


def test_crosses_above():
    # Touching the level is not above it, so 2 -> 3 is a cross.
    rule = {"left": CLOSE, "op": "crosses_above", "right": {"value": 2}}

    assert holds(rule, close=[1, 2, 3, 2, 3, 4]) == [F, F, T, F, T, F]


def test_crosses_below():
    rule = {"left": CLOSE, "op": "crosses_below", "right": {"value": 2}}

    assert holds(rule, close=[3, 1, 2, 1, 1, 0]) == [F, T, F, T, F, F]


@pytest.mark.parametrize(
    ("op", "open_"),
    [("crosses_above", [NAN, 3, 1, 3]), ("crosses_below", [NAN, 1, 3, 1])],
)
def test_there_is_no_cross_on_the_first_valid_bar(op, open_):
    # On bar 1 the open is already past the close, but nothing came before to cross from.
    rule = {"left": OPEN, "op": op, "right": CLOSE}

    assert holds(rule, open=open_, close=[2, 2, 2, 2]) == [F, F, F, T]


def test_all_and_any():
    above_1 = {"left": CLOSE, "op": ">", "right": {"value": 1}}
    below_4 = {"left": CLOSE, "op": "<", "right": {"value": 4}}

    assert holds({"all": [above_1, below_4]}, close=[1, 2, 3, 4]) == [F, T, T, F]
    assert holds({"any": [above_1, below_4]}, close=[1, 2, 3, 4]) == [T, T, T, T]


def test_nested_groups():
    # close > 1 and (close < 2.5 or close > 3.5)
    rule = {
        "all": [
            {"left": CLOSE, "op": ">", "right": {"value": 1}},
            {
                "any": [
                    {"left": CLOSE, "op": "<", "right": {"value": 2.5}},
                    {"left": CLOSE, "op": ">", "right": {"value": 3.5}},
                ]
            },
        ]
    }

    assert holds(rule, close=[1, 2, 3, 4]) == [F, T, F, T]


def test_entry_and_exit_rules_share_indicators(indicator_calls):
    definition = StrategyDefinition.model_validate(
        {
            "direction": "long",
            "entry": {"left": {"indicator": "rsi"}, "op": "<", "right": {"value": 30}},
            "exit": {"left": {"indicator": "rsi"}, "op": ">", "right": {"value": 70}},
        }
    )

    strategy_signals(definition, random_bars())

    assert indicator_calls == ["rsi"]


def test_without_an_exit_rule_there_are_no_exit_signals():
    entries, exits = strategy_signals(
        StrategyDefinition.model_validate(MINIMAL_DEFINITION), random_bars()
    )

    assert entries.dtype == bool
    assert len(entries) == 300
    assert exits is None


MACD = {"indicator": "macd", "fast": 3, "slow": 8, "signal": 4}
BBANDS = {"indicator": "bbands", "period": 10}

# Every indicator, output, price field and operator, earlier bars too, with short periods so
# that all of them matter within a few dozen bars.
EVERY_RULE = {
    "direction": "long",
    "entry": {
        "any": [
            {
                "all": [
                    {"left": {"indicator": "rsi", "period": 5}, "op": "<", "right": {"value": 45}},
                    {
                        "left": CLOSE,
                        "op": "crosses_above",
                        "right": {"indicator": "sma", "period": 10},
                    },
                ]
            },
            {
                "all": [
                    {"left": {"price": "low"}, "op": "<", "right": {"price": "low", "bars_ago": 1}},
                    {
                        "left": {"indicator": "rsi", "period": 5},
                        "op": ">",
                        "right": {"indicator": "rsi", "period": 5, "bars_ago": 2},
                    },
                    {
                        "left": {"divide": [CLOSE, {"price": "open", "bars_ago": 1}]},
                        "op": "<",
                        "right": {"subtract": [{"value": 1.01}, {"value": 0.005}]},
                    },
                ]
            },
            {"left": MACD, "op": "crosses_above", "right": MACD | {"output": "signal"}},
            {"left": {"price": "low"}, "op": "<=", "right": BBANDS | {"output": "lower"}},
        ]
    },
    "exit": {
        "any": [
            {"left": {"indicator": "rsi", "period": 5}, "op": ">=", "right": {"value": 60}},
            {
                "left": {"indicator": "ema", "period": 5, "source": "open"},
                "op": "crosses_below",
                "right": BBANDS | {"output": "middle"},
            },
            {"left": {"price": "high"}, "op": ">", "right": BBANDS | {"output": "upper"}},
            {"left": MACD | {"output": "histogram"}, "op": "<", "right": {"value": -0.5}},
            {"left": {"price": "volume"}, "op": ">", "right": {"value": 9.8}},
            {
                "left": CLOSE,
                "op": "<",
                "right": {
                    "multiply": [
                        {"add": [{"indicator": "sma", "period": 10}, {"value": -0.5}]},
                        {"value": 0.97},
                    ]
                },
            },
        ]
    },
}


def test_signals_never_look_ahead():
    definition = StrategyDefinition.model_validate(EVERY_RULE)
    bars = random_bars(120)
    entries, exits = strategy_signals(definition, bars)
    # Guard against a vacuous pass: both kinds of signal really fire and really don't.
    assert 0 < entries.sum() < len(bars)
    assert 0 < exits.sum() < len(bars)

    for t in range(len(bars)):
        early_entries, early_exits = strategy_signals(definition, bars.iloc[: t + 1])

        np.testing.assert_array_equal(early_entries, entries[: t + 1])
        np.testing.assert_array_equal(early_exits, exits[: t + 1])
