import math

import numpy as np
import pandas as pd
import pytest
from pydantic import TypeAdapter

from app.backtest import indicators
from app.backtest.signals import OperandResolver, evaluate
from app.strategies.rules import Node, Operand
from tests.helpers import random_bars

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


def test_each_indicator_is_computed_once(monkeypatch):
    calls: list[str] = []

    def spy(name):
        original = getattr(indicators, name)

        def counted(*args):
            calls.append(name)
            return original(*args)

        return counted

    monkeypatch.setattr(indicators, "rsi", spy("rsi"))
    monkeypatch.setattr(indicators, "macd", spy("macd"))
    resolver = OperandResolver(random_bars())

    for operand in [
        {"indicator": "rsi", "period": 14},
        {"indicator": "rsi"},  # equal to the first once defaults are filled in
        {"indicator": "rsi", "period": 7},
        {"indicator": "macd", "output": "line"},
        {"indicator": "macd", "output": "signal"},  # same MACD, another of its lines
    ]:
        resolver.resolve(parse_operand(operand))

    assert sorted(calls) == ["macd", "rsi", "rsi"]


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
