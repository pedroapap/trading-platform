import pytest
from pydantic import TypeAdapter, ValidationError

from app.strategies.rules import Bbands, Macd, Operand, Price, Rsi, Sma, Value

operand = TypeAdapter(Operand)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"value": 30}, Value(value=30)),
        ({"price": "close"}, Price(price="close")),
        ({"indicator": "sma", "period": 50}, Sma(indicator="sma", period=50)),
        ({"indicator": "rsi"}, Rsi(indicator="rsi", period=14)),
        (
            {"indicator": "macd", "output": "histogram"},
            Macd(indicator="macd", fast=12, slow=26, signal=9, output="histogram"),
        ),
        (
            {"indicator": "bbands", "period": 20, "std": 2.5, "output": "lower"},
            Bbands(indicator="bbands", period=20, std=2.5, output="lower"),
        ),
    ],
)
def test_operands_parse_with_defaults(data, expected):
    assert operand.validate_python(data) == expected


def test_identical_operands_are_equal_and_hashable():
    first = operand.validate_python({"indicator": "ema", "period": 20})
    second = operand.validate_python({"indicator": "ema", "period": 20, "source": "close"})

    assert first == second
    assert len({first, second}) == 1


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"indicator": "vwap"}, "does not match any of the expected tags: 'sma', 'ema', 'rsi'"),
        ({"indicator": "sma", "period": 0}, "greater than or equal to 1"),
        ({"indicator": "sma"}, "Field required"),
        ({"indicator": "rsi", "period": 1}, "greater than or equal to 2"),
        ({"indicator": "macd", "fast": 26, "slow": 12}, "fast period must be shorter"),
        ({"indicator": "bbands", "std": 0}, "greater than 0"),
        ({"indicator": "sma", "period": 5, "lenght": 3}, "Extra inputs are not permitted"),
        ({"price": "vwap"}, "Input should be 'open', 'high', 'low', 'close' or 'volume'"),
        ({"value": float("nan")}, "finite number"),
        ({"threshold": 30}, "An operand needs a 'value', 'price' or 'indicator' key"),
    ],
)
def test_invalid_operands_are_rejected(data, message):
    with pytest.raises(ValidationError, match=message):
        operand.validate_python(data)
