import time

import pytest

from app.backtest.engine import BacktestConfig, run
from app.backtest.metrics import summarize
from app.strategies.definition import StrategyDefinition
from tests.helpers import random_bars

MINUTES_IN_A_YEAR = 365 * 24 * 60


@pytest.mark.slow
def test_a_year_of_minute_bars_backtests_in_under_five_seconds():
    bars = random_bars(MINUTES_IN_A_YEAR)
    definition = StrategyDefinition.model_validate(
        {
            "direction": "long",
            "entry": {
                "any": [
                    {"left": {"indicator": "rsi"}, "op": "<", "right": {"value": 30}},
                    {
                        "left": {"price": "close"},
                        "op": "crosses_above",
                        "right": {"indicator": "bbands", "output": "lower"},
                    },
                ]
            },
            "exit": {
                "any": [
                    {"left": {"indicator": "rsi"}, "op": ">", "right": {"value": 70}},
                    {
                        "left": {"indicator": "macd", "output": "histogram"},
                        "op": "crosses_below",
                        "right": {"value": 0},
                    },
                ]
            },
            "stop_loss_pct": 2,
            "take_profit_pct": 3,
        }
    )
    config = BacktestConfig(10_000, position_size_pct=90, fee_pct=0.1, slippage_pct=0.05)

    start = time.perf_counter()
    summary = summarize(run(bars, definition, config))
    elapsed = time.perf_counter() - start

    assert summary.num_trades > 1_000  # a realistic amount of work
    assert elapsed < 5, f"took {elapsed:.1f} s"
