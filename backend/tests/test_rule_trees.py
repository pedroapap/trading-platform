import pytest
from pydantic import TypeAdapter, ValidationError

from app.strategies.rules import (
    AllOf,
    AnyOf,
    Condition,
    Node,
    Price,
    Value,
    check_limits,
    conditions,
    depth,
)

node = TypeAdapter(Node)

RSI_BELOW_30 = {"left": {"indicator": "rsi"}, "op": "<", "right": {"value": 30}}
CLOSE_CROSSES_SMA = {
    "left": {"price": "close"},
    "op": "crosses_above",
    "right": {"indicator": "sma", "period": 50},
}


def test_a_condition_parses():
    condition = node.validate_python(CLOSE_CROSSES_SMA)

    assert isinstance(condition, Condition)
    assert condition.left == Price(price="close")
    assert condition.op == "crosses_above"


def test_groups_nest_and_can_be_walked():
    tree = node.validate_python({"all": [RSI_BELOW_30, {"any": [CLOSE_CROSSES_SMA, RSI_BELOW_30]}]})

    assert isinstance(tree, AllOf)
    assert isinstance(tree.all[1], AnyOf)
    assert [c.op for c in conditions(tree)] == ["<", "crosses_above", "<"]
    assert depth(tree) == 3


def test_trees_round_trip_through_json():
    tree = node.validate_python({"any": [RSI_BELOW_30, CLOSE_CROSSES_SMA]})

    assert node.validate_json(node.dump_json(tree)) == tree
    assert hash(tree) == hash(node.validate_python({"any": [RSI_BELOW_30, CLOSE_CROSSES_SMA]}))


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"left": {"value": 1}, "op": "<", "right": {"value": 2}}, "must involve a price or"),
        ({**RSI_BELOW_30, "op": "=="}, "Input should be '<', '<=', '>', '>='"),
        ({"all": []}, "a group needs at least one rule"),
        ({"none": [RSI_BELOW_30]}, "A rule is a condition"),
        ({"all": [RSI_BELOW_30], "any": [RSI_BELOW_30]}, "Extra inputs are not permitted"),
    ],
)
def test_invalid_trees_are_rejected(data, message):
    with pytest.raises(ValidationError, match=message):
        node.validate_python(data)


def nested(levels: int) -> dict:
    tree: dict = RSI_BELOW_30
    for _ in range(levels):
        tree = {"all": [tree]}
    return tree


def test_limits_allow_four_levels_and_twenty_conditions():
    check_limits(node.validate_python(nested(3)))
    check_limits(node.validate_python({"any": [RSI_BELOW_30] * 20}))


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (nested(4), "at most 4 levels deep"),
        ({"any": [RSI_BELOW_30] * 21}, "at most 20 conditions"),
    ],
)
def test_limits_reject_oversized_trees(data, message):
    with pytest.raises(ValueError, match=message):
        check_limits(node.validate_python(data))


def test_constants_may_be_compared_with_prices():
    condition = node.validate_python(
        {"left": {"price": "close"}, "op": "crosses_below", "right": {"value": 100}}
    )

    assert condition.right == Value(value=100)
