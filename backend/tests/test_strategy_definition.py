import pytest
from pydantic import ValidationError

from app.enums import Direction
from app.strategies.definition import StrategyDefinition
from app.strategies.rules import AllOf

RSI_BELOW_30 = {"left": {"indicator": "rsi"}, "op": "<", "right": {"value": 30}}
RSI_ABOVE_70 = {"left": {"indicator": "rsi"}, "op": ">", "right": {"value": 70}}

EXAMPLE = {
    "direction": "long",
    "entry": {
        "all": [
            RSI_BELOW_30,
            {
                "left": {"price": "close"},
                "op": "crosses_above",
                "right": {"indicator": "sma", "period": 50},
            },
        ]
    },
    "exit": {"any": [RSI_ABOVE_70]},
    "stop_loss_pct": 2,
    "take_profit_pct": 6,
}


def definition(**overrides) -> StrategyDefinition:
    return StrategyDefinition.model_validate(EXAMPLE | overrides)


def test_the_documented_example_parses_and_round_trips():
    parsed = definition()

    assert parsed.direction is Direction.LONG
    assert isinstance(parsed.entry, AllOf)
    assert StrategyDefinition.model_validate(parsed.model_dump(mode="json")) == parsed


@pytest.mark.parametrize(
    "overrides",
    [
        {"exit": None},  # a stop-loss or take-profit is enough
        {"exit": None, "stop_loss_pct": None},
        {"take_profit_pct": 150},  # a long can more than double
        {"direction": "short", "stop_loss_pct": 150, "take_profit_pct": 50},
    ],
)
def test_valid_variations(overrides):
    definition(**overrides)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"exit": None, "stop_loss_pct": None, "take_profit_pct": None},
            "needs an exit rule, a stop-loss or a take-profit",
        ),
        ({"stop_loss_pct": 0}, "greater than 0"),
        ({"stop_loss_pct": 100}, "a long stop-loss must be below 100%"),
        ({"direction": "short", "take_profit_pct": 100}, "a short take-profit must be below 100%"),
        ({"direction": "sideways"}, "Input should be 'long' or 'short'"),
        ({"entry": None}, "A rule is a condition"),
        ({"entry": {"all": [{"all": [{"all": [{"all": [RSI_BELOW_30]}]}]}]}}, "at most 4 levels"),
        ({"leverage": 3}, "Extra inputs are not permitted"),
    ],
)
def test_invalid_definitions_are_rejected(overrides, message):
    with pytest.raises(ValidationError, match=message):
        definition(**overrides)
