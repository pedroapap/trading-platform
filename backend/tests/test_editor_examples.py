"""The strategy editor offers examples (frontend/src/examples.json): each must be a valid
definition that trades."""

import json
from pathlib import Path

import pytest

from app.backtest.engine import BacktestConfig, run
from app.strategies.definition import StrategyDefinition
from tests.helpers import DOUBLE_BOTTOM, double_bottom_bars, random_bars

EXAMPLES = json.loads(
    (Path(__file__).parents[2] / "frontend" / "src" / "examples.json").read_text()
)

# A random walk gives every example trades, except the double bottom: it needs its planted bars.
BARS = {"Double bottom after a dip": double_bottom_bars}


@pytest.mark.parametrize("example", EXAMPLES, ids=[example["name"] for example in EXAMPLES])
def test_each_example_is_a_definition_that_trades(example):
    definition = StrategyDefinition.model_validate(example["definition"])
    bars = BARS.get(example["name"], lambda: random_bars(5_000))()

    result = run(bars, definition, BacktestConfig(10_000))

    assert result.trades


def test_the_double_bottom_example_is_the_strategy_tested_end_to_end():
    [example] = [each for each in EXAMPLES if each["name"] in BARS]

    assert example["definition"] == DOUBLE_BOTTOM
