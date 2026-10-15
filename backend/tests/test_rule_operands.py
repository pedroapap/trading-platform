import pytest
from pydantic import TypeAdapter, ValidationError

from app.strategies.rules import (
    Atr,
    Bbands,
    Divide,
    Highest,
    Lowest,
    Macd,
    Multiply,
    Operand,
    Price,
    Rsi,
    Sma,
    Subtract,
    SwingHigh,
    SwingLow,
    Value,
)

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
        ({"indicator": "atr"}, Atr(indicator="atr", period=14)),
        (
            {"indicator": "lowest", "period": 20},
            Lowest(indicator="lowest", period=20, source="low"),
        ),
        (
            {"indicator": "highest", "period": 20, "source": "close"},
            Highest(indicator="highest", period=20, source="close"),
        ),
        (
            {"indicator": "swing_low", "strength": 3},
            SwingLow(indicator="swing_low", strength=3, occurrence=0, output="price", source="low"),
        ),
        (
            {"indicator": "swing_high", "strength": 5, "occurrence": 1, "output": "bars_since"},
            SwingHigh(indicator="swing_high", strength=5, occurrence=1, output="bars_since"),
        ),
        ({"price": "low", "bars_ago": 1}, Price(price="low", bars_ago=1)),
        (
            {"indicator": "sma", "period": 50, "bars_ago": 10},
            Sma(indicator="sma", period=50, bars_ago=10),
        ),
        (
            {"multiply": [{"indicator": "sma", "period": 50}, {"value": 0.98}]},
            Multiply(multiply=(Sma(indicator="sma", period=50), Value(value=0.98))),
        ),
        (
            {"subtract": [{"price": "close"}, {"divide": [{"price": "high"}, {"value": 2}]}]},
            Subtract(
                subtract=(
                    Price(price="close"),
                    Divide(divide=(Price(price="high"), Value(value=2))),
                )
            ),
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


def nested_arithmetic(levels: int) -> dict:
    """`close + 1 + 1 ...`, each addition wrapping the last."""
    data: dict = {"price": "close"}
    for _ in range(levels):
        data = {"add": [data, {"value": 1}]}
    return data


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"indicator": "vwap"}, "does not match any of the expected tags: 'sma', 'ema', 'rsi'"),
        ({"indicator": "sma", "period": 0}, "greater than or equal to 1"),
        ({"indicator": "sma"}, "Field required"),
        ({"indicator": "rsi", "period": 1}, "greater than or equal to 2"),
        ({"indicator": "macd", "fast": 26, "slow": 12}, "fast period must be shorter"),
        ({"indicator": "bbands", "std": 0}, "greater than 0"),
        ({"indicator": "atr", "source": "close"}, "Extra inputs are not permitted"),
        ({"indicator": "lowest"}, "Field required"),
        ({"indicator": "swing_low"}, "Field required"),
        ({"indicator": "swing_low", "strength": 0}, "greater than or equal to 1"),
        ({"indicator": "swing_high", "strength": 3, "occurrence": 10}, "less than or equal to 9"),
        ({"indicator": "swing_low", "strength": 3, "output": "time"}, "'price' or 'bars_since'"),
        ({"indicator": "sma", "period": 5, "lenght": 3}, "Extra inputs are not permitted"),
        ({"price": "vwap"}, "Input should be 'open', 'high', 'low', 'close' or 'volume'"),
        ({"value": float("nan")}, "finite number"),
        ({"price": "low", "bars_ago": -1}, "greater than or equal to 0"),
        ({"indicator": "rsi", "bars_ago": 1001}, "less than or equal to 1000"),
        ({"value": 30, "bars_ago": 1}, "Extra inputs are not permitted"),
        ({"threshold": 30}, "An operand needs a 'value', 'price', 'indicator', 'add',"),
        ({"power": [{"value": 2}, {"price": "close"}]}, "or 'divide' key"),
        ({"add": [{"price": "close"}]}, "arithmetic takes exactly two operands"),
        ({"add": [{"value": 1}] * 3}, "arithmetic takes exactly two operands"),
        ({"add": [{"price": "close"}, {"value": 1}], "bars_ago": 1}, "Extra inputs"),
        (nested_arithmetic(5), "arithmetic may be nested at most 4 levels deep"),
    ],
)
def test_invalid_operands_are_rejected(data, message):
    with pytest.raises(ValidationError, match=message):
        operand.validate_python(data)


def test_bars_ago_is_only_stored_when_set():
    # Definitions written before `bars_ago` existed dump exactly as they did.
    assert operand.dump_python(Price(price="low"), mode="json") == {"price": "low"}
    assert operand.dump_python(Price(price="low", bars_ago=2), mode="json") == {
        "price": "low",
        "bars_ago": 2,
    }


def test_arithmetic_may_nest_four_levels_deep():
    operand.validate_python(nested_arithmetic(4))


def test_an_invalid_operand_inside_arithmetic_is_the_only_error():
    with pytest.raises(ValidationError) as caught:
        operand.validate_python({"multiply": [{"indicator": "sma", "period": 0}, {"value": 2}]})

    [error] = caught.value.errors()
    assert error["loc"] == ("multiply", "multiply", 0, "indicator", "sma", "period")
