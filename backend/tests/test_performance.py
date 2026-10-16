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


@pytest.mark.slow
def test_limit_orders_on_every_bar_backtest_in_under_five_seconds():
    # A new order on every bar, each replacing the last: the engine must still only work per
    # trade, not per bar.
    bars = random_bars(MINUTES_IN_A_YEAR)
    definition = StrategyDefinition.model_validate(
        {
            "direction": "long",
            "entry": {"left": {"price": "close"}, "op": ">", "right": {"value": 0}},
            "entry_order": {
                "type": "limit",
                "price": {"multiply": [{"price": "close"}, {"value": 0.999}]},
                "expires_after": 5,
            },
            "stop_loss_pct": 2,
            "take_profit_pct": 3,
        }
    )
    config = BacktestConfig(10_000, fee_pct=0.1, slippage_pct=0.05)

    start = time.perf_counter()
    summary = summarize(run(bars, definition, config))
    elapsed = time.perf_counter() - start

    assert summary.num_trades > 1_000
    assert elapsed < 5, f"took {elapsed:.1f} s"


@pytest.mark.slow
def test_every_new_block_backtests_a_year_in_under_five_seconds():
    # A double bottom after a new low, so swings, patterns, events and arithmetic; a limit
    # entry, a stop under the swing low, a 2R target, a chandelier trailing stop and a time
    # exit. (The test above covers many more trades, each costing about the same.)
    bars = random_bars(MINUTES_IN_A_YEAR)
    atr = {"indicator": "atr", "period": 14}
    definition = StrategyDefinition.model_validate(
        {
            "direction": "long",
            "entry": {
                "all": [
                    {"pattern": "equal_lows", "strength": 3, "within": 60, "tolerance_pct": 0.2},
                    {
                        "happened": {
                            "left": {"price": "low"},
                            "op": "<",
                            "right": {"indicator": "lowest", "period": 20, "bars_ago": 1},
                        },
                        "within": 10,
                    },
                ]
            },
            "entry_order": {
                "type": "limit",
                "price": {
                    "multiply": [{"indicator": "swing_low", "strength": 3}, {"value": 1.003}]
                },
                "expires_after": 6,
            },
            "stop_loss_at": {"subtract": [{"indicator": "swing_low", "strength": 3}, atr]},
            "take_profit_r": 2,
            "trailing_stop_at": {
                "subtract": [
                    {"indicator": "highest", "period": 22},
                    {"multiply": [atr, {"value": 3}]},
                ]
            },
            "exit_after_bars": 240,
        }
    )
    config = BacktestConfig(10_000, fee_pct=0.1, slippage_pct=0.05)

    start = time.perf_counter()
    summary = summarize(run(bars, definition, config))
    elapsed = time.perf_counter() - start

    assert summary.num_trades > 1_000
    assert elapsed < 5, f"took {elapsed:.1f} s"


@pytest.mark.slow
def test_the_day_trading_blocks_backtest_a_year_in_under_five_seconds():
    # An opening-range breakout on a New York session, in a morning window above VWAP and the
    # daily trend, out by 15:55: sessions, VWAP, the opening range, a daily wrapper and flat_at.
    bars = random_bars(MINUTES_IN_A_YEAR)
    opening_range = {"indicator": "opening_range", "minutes": 30}
    definition = StrategyDefinition.model_validate(
        {
            "direction": "long",
            "session": {"timezone": "America/New_York", "start": "09:30", "end": "16:00"},
            "entry": {
                "all": [
                    {"time": ["10:00", "12:00"]},
                    {"left": {"price": "close"}, "op": ">", "right": {"indicator": "vwap"}},
                    {
                        "left": {"price": "close"},
                        "op": ">",
                        "right": {"timeframe": "1d", "of": {"indicator": "sma", "period": 20}},
                    },
                ]
            },
            "entry_order": {"type": "stop", "price": opening_range | {"output": "high"}},
            "stop_loss_at": opening_range | {"output": "low"},
            "take_profit_r": 2,
            "flat_at": "15:55",
        }
    )
    config = BacktestConfig(10_000, fee_pct=0.1, slippage_pct=0.05)

    start = time.perf_counter()
    summary = summarize(run(bars, definition, config))
    elapsed = time.perf_counter() - start

    assert summary.num_trades > 100
    assert elapsed < 5, f"took {elapsed:.1f} s"
