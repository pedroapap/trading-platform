import numpy as np
import pytest
from pydantic import TypeAdapter

from app.backtest import indicators
from app.backtest.signals import OperandResolver
from app.strategies.rules import Operand
from tests.helpers import random_bars

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
