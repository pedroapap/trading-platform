import math

import numpy as np
import pandas as pd
import pytest
from pydantic import TypeAdapter

from app.backtest import indicators
from app.backtest.orders import Level
from app.backtest.signals import OperandResolver, evaluate, strategy_orders, strategy_signals
from app.enums import Direction
from app.strategies.definition import Session, StrategyDefinition
from app.strategies.rules import Node, Operand
from tests.helpers import MINIMAL_DEFINITION, random_bars

NAN = math.nan

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
        (
            {"indicator": "atr", "period": 5},
            lambda b: indicators.atr(b["high"], b["low"], b["close"], 5),
        ),
        ({"indicator": "lowest", "period": 7}, lambda b: indicators.lowest(b["low"], 7)),
        (
            {"indicator": "highest", "period": 7, "source": "close"},
            lambda b: indicators.highest(b["close"], 7),
        ),
        (
            {"indicator": "swing_low", "strength": 3, "occurrence": 1, "output": "bars_since"},
            lambda b: indicators.swing_low(b["low"], 3, 1)["bars_since"],
        ),
        (
            {"indicator": "swing_high", "strength": 2, "source": "close"},
            lambda b: indicators.swing_high(b["close"], 2)["price"],
        ),
    ],
    ids=[
        "sma",
        "ema",
        "rsi",
        "macd",
        "bbands",
        "atr",
        "lowest",
        "highest",
        "swing_low",
        "swing_high",
    ],
)
def test_an_indicator_is_computed_on_its_source(operand, direct):
    bars = random_bars()

    resolved = OperandResolver(bars).resolve(parse_operand(operand))

    np.testing.assert_array_equal(resolved, direct(bars))


def test_bars_ago_takes_the_value_that_many_bars_earlier():
    bars = random_bars(30)
    resolver = OperandResolver(bars)

    previous_low = resolver.resolve(parse_operand({"price": "low", "bars_ago": 1}))
    sma = resolver.resolve(parse_operand({"indicator": "sma", "period": 5}))
    earlier_sma = resolver.resolve(parse_operand({"indicator": "sma", "period": 5, "bars_ago": 3}))

    np.testing.assert_array_equal(previous_low, [NAN, *bars["low"].iloc[:-1]])
    np.testing.assert_array_equal(earlier_sma, [NAN] * 3 + sma[:-3].tolist())


def test_bars_ago_beyond_the_data_is_unknown():
    resolved = OperandResolver(random_bars(5)).resolve(
        parse_operand({"price": "close", "bars_ago": 9})
    )

    assert np.isnan(resolved).all()


@pytest.mark.parametrize(
    ("operation", "expected"),
    [("add", [5.0, 7.0]), ("subtract", [-3.0, -3.0]), ("multiply", [4.0, 10.0])],
)
def test_arithmetic_combines_two_operands(operation, expected):
    bars = pd.DataFrame({"open": [1.0, 2.0], "close": [4.0, 5.0]})
    data = {operation: [{"price": "open"}, {"price": "close"}]}

    assert OperandResolver(bars).resolve(parse_operand(data)).tolist() == expected


def test_dividing_by_zero_is_unknown():
    bars = pd.DataFrame({"open": [1.0, 0.0, -2.0], "close": [3.0, 3.0, 0.0]})

    quotient = OperandResolver(bars).resolve(
        parse_operand({"divide": [{"price": "close"}, {"price": "open"}]})
    )

    np.testing.assert_array_equal(quotient, [3.0, NAN, -0.0])


@pytest.fixture
def indicator_calls(monkeypatch) -> list[str]:
    """Calls to `indicators.rsi`, `indicators.macd` and `indicators.swing_low` during the test,
    in order. (Not SMA or EMA: MACD and Bollinger Bands call those internally.)"""
    calls: list[str] = []

    def spy(name):
        original = getattr(indicators, name)

        def counted(*args):
            calls.append(name)
            return original(*args)

        return counted

    monkeypatch.setattr(indicators, "rsi", spy("rsi"))
    monkeypatch.setattr(indicators, "macd", spy("macd"))
    monkeypatch.setattr(indicators, "swing_low", spy("swing_low"))
    return calls


def test_each_indicator_is_computed_once(indicator_calls):
    resolver = OperandResolver(random_bars())

    for operand in [
        {"indicator": "rsi", "period": 14},
        {"indicator": "rsi"},  # equal to the first once defaults are filled in
        {"indicator": "rsi", "period": 7},
        {"indicator": "macd", "output": "line"},
        {"indicator": "macd", "output": "signal"},  # same MACD, another of its lines
        {"indicator": "rsi", "bars_ago": 3},  # the first RSI, shifted
        {"indicator": "macd", "output": "histogram", "bars_ago": 1},
        {"indicator": "swing_low", "strength": 3},
        {"indicator": "swing_low", "strength": 3, "output": "bars_since"},  # same swings
    ]:
        resolver.resolve(parse_operand(operand))

    assert sorted(indicator_calls) == ["macd", "rsi", "rsi", "swing_low"]


parse_rule = TypeAdapter(Node).validate_python

CLOSE = {"price": "close"}
OPEN = {"price": "open"}
T, F = True, False


def holds(rule: dict, **columns: list[float]) -> list[bool]:
    bars = pd.DataFrame({name: np.array(values, dtype=float) for name, values in columns.items()})
    return evaluate(parse_rule(rule), OperandResolver(bars)).tolist()


@pytest.mark.parametrize(
    ("op", "expected"),
    [("<", [T, F, F]), ("<=", [T, T, F]), (">", [F, F, T]), (">=", [F, T, T])],
)
def test_comparison(op, expected):
    assert holds({"left": CLOSE, "op": op, "right": {"value": 2}}, close=[1, 2, 3]) == expected


@pytest.mark.parametrize("op", ["<", "<=", ">", ">="])
def test_a_comparison_with_a_missing_value_is_false(op):
    rule = {"left": OPEN, "op": op, "right": CLOSE}

    assert holds(rule, open=[NAN, 2, NAN], close=[2, NAN, NAN]) == [F, F, F]


def test_a_comparison_with_a_division_by_zero_is_false():
    rule = {"left": {"divide": [CLOSE, OPEN]}, "op": ">", "right": {"value": 0}}

    assert holds(rule, open=[1, 0], close=[3, 3]) == [T, F]


GT_2 = {"left": CLOSE, "op": ">", "right": {"value": 2}}


def test_not_is_false_until_its_values_are_known():
    # SMA(2) is unknown on the first bar: neither the rule nor its negation holds there.
    sma_above_2 = {"left": {"indicator": "sma", "period": 2}, "op": ">", "right": {"value": 2}}

    assert holds({"not": sma_above_2}, close=[1, 2, 3, 1]) == [F, T, F, T]


def test_not_of_a_cross_waits_for_the_previous_bar():
    rule = {"not": {"left": CLOSE, "op": "crosses_above", "right": {"value": 2}}}

    assert holds(rule, close=[1, 3, 3]) == [F, F, T]


def test_happened_looks_back_over_the_window():
    rule = {"happened": GT_2, "within": 3}

    assert holds(rule, close=[3, 1, 1, 1, 3, 1]) == [T, T, T, F, T, T]


def test_happened_counts_separate_runs():
    rule = {"happened": GT_2, "within": 4, "times": 2}

    # Runs start on bars 0, 2 and 6; two of them are within 4 bars only on bars 2 and 3.
    assert holds(rule, close=[3, 1, 3, 1, 1, 1, 3]) == [F, F, T, T, F, F, F]


def test_a_run_that_began_before_the_window_counts():
    rule = {"happened": GT_2, "within": 3, "times": 2}

    assert holds(rule, close=[3, 3, 1, 3]) == [F, F, F, T]


def test_a_long_run_counts_once():
    rule = {"happened": GT_2, "within": 4, "times": 2}

    assert holds(rule, close=[3, 3, 3, 3]) == [F, F, F, F]


def test_not_happened_waits_for_a_whole_window():
    rule = {"not": {"happened": GT_2, "within": 3}}

    assert holds(rule, close=[1, 1, 1, 1, 3]) == [F, F, T, T, F]


def test_a_pattern_holds_where_it_is_confirmed():
    lows = [10, 9, 8, 9, 10, 9.5, 9, 9.5, 10, 9, 8.02, 9, 10]
    double_bottom = {"pattern": "equal_lows", "strength": 2, "within": 10, "tolerance_pct": 0.5}

    assert holds(double_bottom, low=lows) == [F] * 12 + [T]
    # Nothing in a pattern is unknown, so its negation holds everywhere else.
    assert holds({"not": double_bottom}, low=lows) == [T] * 12 + [F]


def test_crosses_above():
    # Touching the level is not above it, so 2 -> 3 is a cross.
    rule = {"left": CLOSE, "op": "crosses_above", "right": {"value": 2}}

    assert holds(rule, close=[1, 2, 3, 2, 3, 4]) == [F, F, T, F, T, F]


def test_crosses_below():
    rule = {"left": CLOSE, "op": "crosses_below", "right": {"value": 2}}

    assert holds(rule, close=[3, 1, 2, 1, 1, 0]) == [F, T, F, T, F, F]


@pytest.mark.parametrize(
    ("op", "open_"),
    [("crosses_above", [NAN, 3, 1, 3]), ("crosses_below", [NAN, 1, 3, 1])],
)
def test_there_is_no_cross_on_the_first_valid_bar(op, open_):
    # On bar 1 the open is already past the close, but nothing came before to cross from.
    rule = {"left": OPEN, "op": op, "right": CLOSE}

    assert holds(rule, open=open_, close=[2, 2, 2, 2]) == [F, F, F, T]


def test_all_and_any():
    above_1 = {"left": CLOSE, "op": ">", "right": {"value": 1}}
    below_4 = {"left": CLOSE, "op": "<", "right": {"value": 4}}

    assert holds({"all": [above_1, below_4]}, close=[1, 2, 3, 4]) == [F, T, T, F]
    assert holds({"any": [above_1, below_4]}, close=[1, 2, 3, 4]) == [T, T, T, T]


def test_nested_groups():
    # close > 1 and (close < 2.5 or close > 3.5)
    rule = {
        "all": [
            {"left": CLOSE, "op": ">", "right": {"value": 1}},
            {
                "any": [
                    {"left": CLOSE, "op": "<", "right": {"value": 2.5}},
                    {"left": CLOSE, "op": ">", "right": {"value": 3.5}},
                ]
            },
        ]
    }

    assert holds(rule, close=[1, 2, 3, 4]) == [F, T, F, T]


def test_entry_and_exit_rules_share_indicators(indicator_calls):
    definition = StrategyDefinition.model_validate(
        {
            "direction": "long",
            "entry": {"left": {"indicator": "rsi"}, "op": "<", "right": {"value": 30}},
            "exit": {"left": {"indicator": "rsi"}, "op": ">", "right": {"value": 70}},
        }
    )

    strategy_signals(definition, random_bars())

    assert indicator_calls == ["rsi"]


def test_orders_carry_the_signals_and_the_definitions_levels():
    definition = StrategyDefinition.model_validate(MINIMAL_DEFINITION | {"take_profit_pct": 6})
    bars = random_bars(300)

    orders = strategy_orders(definition, bars)

    entries, exits = strategy_signals(definition, bars)
    np.testing.assert_array_equal(orders.entries, entries)
    assert orders.exits is exits is None
    assert orders.direction == Direction.LONG
    assert (orders.stop_loss, orders.take_profit) == (Level(pct=2), Level(pct=6))


def test_without_an_exit_rule_there_are_no_exit_signals():
    entries, exits = strategy_signals(
        StrategyDefinition.model_validate(MINIMAL_DEFINITION), random_bars()
    )

    assert entries.dtype == bool
    assert len(entries) == 300
    assert exits is None


MACD = {"indicator": "macd", "fast": 3, "slow": 8, "signal": 4}
BBANDS = {"indicator": "bbands", "period": 10}

# Every indicator, output, price field and operator, earlier bars too, with short periods so
# that all of them matter within a few dozen bars.
EVERY_RULE = {
    "direction": "long",
    "entry": {
        "any": [
            {
                "all": [
                    {"left": {"indicator": "rsi", "period": 5}, "op": "<", "right": {"value": 45}},
                    {
                        "left": CLOSE,
                        "op": "crosses_above",
                        "right": {"indicator": "sma", "period": 10},
                    },
                ]
            },
            {
                "all": [
                    {"left": {"price": "low"}, "op": "<", "right": {"price": "low", "bars_ago": 1}},
                    {
                        "left": {"indicator": "rsi", "period": 5},
                        "op": ">",
                        "right": {"indicator": "rsi", "period": 5, "bars_ago": 2},
                    },
                    {
                        "left": {"divide": [CLOSE, {"price": "open", "bars_ago": 1}]},
                        "op": "<",
                        "right": {"subtract": [{"value": 1.01}, {"value": 0.005}]},
                    },
                ]
            },
            {"left": MACD, "op": "crosses_above", "right": MACD | {"output": "signal"}},
            {
                "all": [
                    {
                        "happened": {
                            "left": CLOSE,
                            "op": "crosses_above",
                            "right": {
                                "indicator": "highest",
                                "period": 8,
                                "source": "close",
                                "bars_ago": 1,
                            },
                        },
                        "within": 4,
                    },
                    {
                        "not": {
                            "left": {"indicator": "rsi", "period": 5},
                            "op": ">",
                            "right": {"value": 70},
                        }
                    },
                ]
            },
            {
                "left": {"price": "low"},
                "op": "<=",
                "right": {
                    "multiply": [
                        {"indicator": "swing_low", "strength": 2, "occurrence": 1},
                        {"value": 1.002},
                    ]
                },
            },
            {"left": {"price": "low"}, "op": "<=", "right": BBANDS | {"output": "lower"}},
            {"pattern": "equal_lows", "strength": 2, "within": 30, "tolerance_pct": 0.3},
        ]
    },
    "exit": {
        "any": [
            {"left": {"indicator": "rsi", "period": 5}, "op": ">=", "right": {"value": 60}},
            {
                "left": {"indicator": "ema", "period": 5, "source": "open"},
                "op": "crosses_below",
                "right": BBANDS | {"output": "middle"},
            },
            {"left": {"price": "high"}, "op": ">", "right": BBANDS | {"output": "upper"}},
            {"left": MACD | {"output": "histogram"}, "op": "<", "right": {"value": -0.5}},
            {"left": {"price": "volume"}, "op": ">", "right": {"value": 9.8}},
            {
                "left": CLOSE,
                "op": "<",
                "right": {
                    "multiply": [
                        {"add": [{"indicator": "sma", "period": 10}, {"value": -0.5}]},
                        {"value": 0.97},
                    ]
                },
            },
            {
                "left": {"price": "low"},
                "op": "<",
                "right": {
                    "subtract": [
                        {"indicator": "lowest", "period": 5, "bars_ago": 1},
                        {"indicator": "atr", "period": 5},
                    ]
                },
            },
            {
                "happened": {
                    "left": {"indicator": "swing_high", "strength": 2, "output": "bars_since"},
                    "op": "<=",
                    "right": {"value": 2},
                },
                "within": 6,
                "times": 2,
            },
            {"pattern": "equal_highs", "strength": 2, "within": 30, "tolerance_pct": 0.3},
        ]
    },
}


def test_signals_never_look_ahead():
    definition = StrategyDefinition.model_validate(EVERY_RULE)
    bars = random_bars(120)
    entries, exits = strategy_signals(definition, bars)
    # Guard against a vacuous pass: both kinds of signal really fire and really don't.
    assert 0 < entries.sum() < len(bars)
    assert 0 < exits.sum() < len(bars)

    for t in range(len(bars)):
        early_entries, early_exits = strategy_signals(definition, bars.iloc[: t + 1])

        np.testing.assert_array_equal(early_entries, entries[: t + 1])
        np.testing.assert_array_equal(early_exits, exits[: t + 1])


def new_york_bars(*local_times: str) -> pd.DataFrame:
    """Flat bars starting at the given New York times."""
    times = pd.DatetimeIndex(local_times).tz_localize("America/New_York").tz_convert("UTC")
    return pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0}, index=times
    )


NEW_YORK = Session(timezone="America/New_York", start="09:30", end="16:00")
# Half-hour bars on the Friday before and the Monday after clocks went forward.
HALF_HOURS = new_york_bars(
    *[
        f"{day} {time}"
        for day in ("2026-03-06", "2026-03-09")
        for time in ("09:30", "10:00", "10:30", "11:00", "15:30")
    ]
)


@pytest.mark.parametrize(
    ("window", "holds"),
    [
        (["10:00", "11:00"], [False, True, True, False, False]),
        # Wrapping past midnight: from 15:00 until 10:00 the next morning.
        (["15:00", "10:00"], [True, False, False, False, True]),
    ],
)
def test_a_time_window_holds_on_bars_starting_in_it_in_the_sessions_zone(window, holds):
    rule = TypeAdapter(Node).validate_python({"time": window})

    assert evaluate(rule, OperandResolver(HALF_HOURS, NEW_YORK)).tolist() == holds * 2


def test_without_a_session_a_time_window_is_in_utc():
    bars = random_bars(4)  # from 14:30 UTC, a minute apart
    rule = TypeAdapter(Node).validate_python({"time": ["14:31", "14:33"]})

    assert evaluate(rule, OperandResolver(bars)).tolist() == [False, True, True, False]


def test_vwap_follows_the_sessions_trading_days():
    # Hourly bars from 08:00 to 17:00 New York time on two days: 09:00 to 15:00 overlap the
    # session, and VWAP starts again each day.
    times = pd.DatetimeIndex(
        [f"{day} {hour:02}:00" for day in ("2026-03-05", "2026-03-06") for hour in range(8, 18)]
    )
    bars = random_bars(len(times))
    bars.index = times.tz_localize("America/New_York").tz_convert("UTC")
    in_session = np.array([8 < hour < 16 for _ in range(2) for hour in range(8, 18)])

    vwap = OperandResolver(bars, NEW_YORK).resolve(parse_operand({"indicator": "vwap"}))

    expected = indicators.vwap(
        bars["high"], bars["low"], bars["close"], bars["volume"], np.repeat([0, 1], 10), in_session
    )
    np.testing.assert_allclose(vwap, expected, rtol=1e-12, equal_nan=True)
    assert np.isnan(vwap[~in_session]).all()
    # Each day's first bar in the session is its own typical price.
    first = bars.iloc[1]
    assert vwap[1] == pytest.approx((first["high"] + first["low"] + first["close"]) / 3)
    assert vwap[11] == pytest.approx(bars.iloc[11][["high", "low", "close"]].mean())
