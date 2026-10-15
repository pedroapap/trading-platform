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


def six_groups_deep(rule: dict) -> dict:
    for _ in range(6):
        rule = {"all": [rule]}
    return rule


@pytest.mark.parametrize(
    "overrides",
    [
        {"exit": None},  # a stop-loss or take-profit is enough
        {"exit": None, "stop_loss_pct": None},
        {"take_profit_pct": 150},  # a long can more than double
        {"direction": "short", "stop_loss_pct": 150, "take_profit_pct": 50},
        {"stop_loss_pct": None, "stop_loss_at": {"indicator": "swing_low", "strength": 3}},
        {"take_profit_pct": None, "take_profit_r": 2},
        {"take_profit_pct": None, "take_profit_at": {"indicator": "highest", "period": 20}},
        {"entry_order": {"type": "market"}},
        {"exit": None, "stop_loss_pct": None, "take_profit_pct": None, "trailing_stop_pct": 5},
        {"trailing_stop_at": {"indicator": "lowest", "period": 10}},
        {"direction": "short", "trailing_stop_pct": 150},
        {"exit": None, "stop_loss_pct": None, "take_profit_pct": None, "exit_after_bars": 24},
        {
            "entry_order": {
                "type": "limit",
                "price": {
                    "multiply": [{"indicator": "swing_low", "strength": 3}, {"value": 1.003}]
                },
                "expires_after": 6,
            }
        },
        {"entry_order": {"type": "stop", "price": {"indicator": "highest", "period": 20}}},
        # A stop at a fixed price is a way out too.
        {
            "exit": None,
            "stop_loss_pct": None,
            "take_profit_pct": None,
            "stop_loss_at": {"value": 95},
        },
    ],
)
def test_valid_variations(overrides):
    definition(**overrides)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"exit": None, "stop_loss_pct": None, "take_profit_pct": None},
            "needs a way out: an exit rule, a stop-loss, a take-profit, a trailing stop or",
        ),
        ({"stop_loss_pct": 0}, "greater than 0"),
        ({"stop_loss_pct": 100}, "a long stop-loss must be below 100%"),
        ({"direction": "short", "take_profit_pct": 100}, "a short take-profit must be below 100%"),
        ({"direction": "sideways"}, "Input should be 'long' or 'short'"),
        ({"entry": None}, "A rule is a condition"),
        ({"entry": six_groups_deep(RSI_BELOW_30)}, "at most 6 levels"),
        ({"leverage": 3}, "Extra inputs are not permitted"),
        ({"stop_loss_at": {"value": 95}}, "one stop-loss: stop_loss_pct or stop_loss_at"),
        ({"take_profit_r": 2}, "one take-profit: take_profit_pct, take_profit_at or"),
        (
            {"stop_loss_pct": None, "take_profit_pct": None, "take_profit_r": 2},
            "take_profit_r needs a stop-loss",
        ),
        ({"take_profit_pct": None, "take_profit_r": 0}, "greater than 0"),
        ({"take_profit_pct": None, "take_profit_r": 101}, "less than or equal to 100"),
        ({"stop_loss_pct": None, "stop_loss_at": {"indicator": "vwap"}}, "expected tags"),
        ({"entry_order": {"type": "limit"}}, "Field required"),
        ({"entry_order": {"type": "market", "price": {"value": 95}}}, "Extra inputs"),
        (
            {"entry_order": {"type": "stop", "price": {"value": 95}, "expires_after": 0}},
            "greater than or equal to 1",
        ),
        ({"entry_order": {"type": "trailing"}}, "does not match any of the expected tags"),
        (
            {"trailing_stop_pct": 5, "trailing_stop_at": {"price": "low"}},
            "one trailing stop: trailing_stop_pct or trailing_stop_at",
        ),
        ({"trailing_stop_pct": 100}, "a long trailing stop must be below 100%"),
        ({"trailing_stop_pct": 0}, "greater than 0"),
        ({"exit_after_bars": 0}, "greater than or equal to 1"),
    ],
)
def test_invalid_definitions_are_rejected(overrides, message):
    with pytest.raises(ValidationError, match=message):
        definition(**overrides)


def test_levels_are_only_stored_when_set():
    assert set(definition().model_dump(mode="json")) == {
        "direction",
        "entry",
        "exit",
        "stop_loss_pct",
        "take_profit_pct",
    }
    with_levels = definition(
        stop_loss_pct=None,
        stop_loss_at={"price": "low", "bars_ago": 1},
        take_profit_pct=None,
        take_profit_r=2,
    ).model_dump(mode="json")
    assert with_levels["stop_loss_at"] == {"price": "low", "bars_ago": 1}
    assert with_levels["take_profit_r"] == 2
    assert "take_profit_at" not in with_levels
