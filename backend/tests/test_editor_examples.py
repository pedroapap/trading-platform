"""The strategy editor offers examples (frontend/src/examples.json): each must be a valid
definition that trades."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.backtest.engine import BacktestConfig, run
from app.strategies.definition import StrategyDefinition
from tests.helpers import DOUBLE_BOTTOM, double_bottom_bars, random_bars

EXAMPLES = json.loads(
    (Path(__file__).parents[2] / "frontend" / "src" / "examples.json").read_text()
)


def uptrend_bars(days: int = 30) -> pd.DataFrame:
    """Five-minute bars around the clock, rising about 1% a day with 0.2% noise per bar: a
    daily trend filter on a 20-day average passes once 20 days have closed."""
    length = days * 288
    rng = np.random.default_rng(5)
    close = 100 * np.exp(np.cumsum(rng.normal(0.01 / 288, 0.002, length)))
    open_ = np.concatenate([[100.0], close[:-1]])
    spread = close * rng.uniform(0, 0.001, length)
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + spread,
            "low": np.minimum(open_, close) - spread,
            "close": close,
            "volume": rng.uniform(1, 10, length),
        },
        index=pd.date_range("2026-01-01", periods=length, freq="5min", tz="UTC"),
    )


# A random walk gives the first examples trades. The double bottom needs its planted bars,
# and the day trades whole days, a month of them for the daily trend filter.
BARS = {
    "Double bottom after a dip": double_bottom_bars,
    "Opening-range breakout (New York)": uptrend_bars,
    "VWAP pullback in a daily uptrend": uptrend_bars,
}
# The day trades, with the time zone of their trading day.
DAY_TRADES = {
    "Opening-range breakout (New York)": "America/New_York",
    "VWAP pullback in a daily uptrend": "UTC",
}


def backtest(example: dict) -> list:
    definition = StrategyDefinition.model_validate(example["definition"])
    bars = BARS.get(example["name"], lambda: random_bars(5_000))()
    return run(bars, definition, BacktestConfig(10_000)).trades


@pytest.mark.parametrize("example", EXAMPLES, ids=[example["name"] for example in EXAMPLES])
def test_each_example_is_a_definition_that_trades(example):
    assert backtest(example)


@pytest.mark.parametrize(("name", "zone"), DAY_TRADES.items())
def test_a_day_trade_closes_on_the_day_it_opened(name, zone):
    [example] = [each for each in EXAMPLES if each["name"] == name]

    trades = backtest(example)

    assert all(
        trade.entry_time.tz_convert(zone).date() == trade.exit_time.tz_convert(zone).date()
        for trade in trades
    )


def test_the_double_bottom_example_is_the_strategy_tested_end_to_end():
    [example] = [each for each in EXAMPLES if each["name"] == "Double bottom after a dip"]

    assert example["definition"] == DOUBLE_BOTTOM
