"""Golden tests: small bar tables whose trades and equity are worked out by hand."""

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.backtest import indicators
from app.backtest.engine import (
    BacktestConfig,
    Detail,
    SimulatedTrade,
    run,
    simulate,
    simulate_orders,
)
from app.backtest.orders import Entry, Level, Orders
from app.backtest.signals import strategy_signals
from app.enums import Direction, ExitReason
from app.services.pnl import trade_pnl
from app.strategies.definition import StrategyDefinition
from tests.helpers import ENTRY_TIME, finer_bars, random_bars


def bars_from(rows: list[tuple[float, float, float, float]]) -> pd.DataFrame:
    """Bars from (open, high, low, close) rows, one minute apart."""
    bars = pd.DataFrame(rows, columns=["open", "high", "low", "close"], dtype=float)
    bars["volume"] = 1.0
    bars.index = pd.date_range(ENTRY_TIME, periods=len(rows), freq="min")
    return bars


def approx(expected):
    return pytest.approx(expected, rel=1e-12, abs=1e-9)


def at(length: int, *bars: int) -> np.ndarray:
    """A signal array that is true on the given bars."""
    signals = np.zeros(length, dtype=bool)
    signals[list(bars)] = True
    return signals


# fmt: off
TWELVE_BARS = bars_from([
    # open, high, low, close
    (100, 102,  99, 101),  # 0
    (101, 103, 100, 102),  # 1  entry signal
    (100, 105,  99, 104),  # 2  buy 50 @ 100 (half of 10,000)
    (104, 107, 103, 106),  # 3  entry signal ignored: already in a position
    (106, 109, 105, 108),  # 4  exit signal
    (110, 111, 104, 105),  # 5  sell 50 @ 110: +500
    (105, 106, 102, 103),  # 6  entry signal
    (105, 106,  99, 100),  # 7  buy 50 @ 105 (half of 10,500); exit signal on the entry bar
    ( 98, 100,  97,  99),  # 8  sell 50 @ 98: -350; exit signal ignored: no position
    ( 99, 101,  98, 100),  # 9
    (100, 103,  99, 102),  # 10
    (102, 104, 101, 103),  # 11 entry signal ignored: no next bar to fill on
])
# fmt: on
TIMES = TWELVE_BARS.index


def test_long_round_trips_by_hand():
    result = simulate(
        TWELVE_BARS,
        entries=at(12, 1, 3, 6, 11),
        exits=at(12, 4, 7, 8),
        config=BacktestConfig(initial_capital=10_000, position_size_pct=50),
    )

    assert result.trades == [
        SimulatedTrade(
            direction=Direction.LONG,
            entry_time=TIMES[2],
            entry_price=100,
            exit_time=TIMES[5],
            exit_price=110,
            size=50,
            entry_fee=0,
            exit_fee=0,
            slippage=0,
            pnl=500,
            pnl_pct=10,
            exit_reason=ExitReason.SIGNAL,
        ),
        SimulatedTrade(
            direction=Direction.LONG,
            entry_time=TIMES[7],
            entry_price=105,
            exit_time=TIMES[8],
            exit_price=98,
            size=50,
            entry_fee=0,
            exit_fee=0,
            slippage=0,
            pnl=-350,
            pnl_pct=pytest.approx(-350 / 5250 * 100),
            exit_reason=ExitReason.SIGNAL,
        ),
    ]
    # Marked to market at each close: e.g. bar 3 is 10,000 + 50 * (106 - 100).
    assert result.equity.tolist() == [
        10_000, 10_000, 10_200, 10_300, 10_400, 10_500,
        10_500, 10_250, 10_150, 10_150, 10_150, 10_150,
    ]  # fmt: skip
    assert result.equity.index.equals(TIMES)


def test_without_signals_equity_stays_at_the_initial_capital():
    result = simulate(TWELVE_BARS, at(12), None, BacktestConfig(initial_capital=10_000))

    assert result.trades == []
    assert result.equity.tolist() == [10_000] * 12


def test_a_position_open_at_the_end_closes_at_the_last_close():
    # Bar 1's signal buys 100 @ 100 on bar 2 with the whole 10,000; nothing sells.
    result = simulate(TWELVE_BARS, at(12, 1), None, BacktestConfig(initial_capital=10_000))

    assert result.trades == [
        SimulatedTrade(
            direction=Direction.LONG,
            entry_time=TIMES[2],
            entry_price=100,
            exit_time=TIMES[11],
            exit_price=103,
            size=100,
            entry_fee=0,
            exit_fee=0,
            slippage=0,
            pnl=300,
            pnl_pct=3,
            exit_reason=ExitReason.END_OF_DATA,
        )
    ]
    closes = TWELVE_BARS["close"].tolist()
    assert result.equity.tolist() == [10_000, 10_000] + [100 * close for close in closes[2:]]


def test_a_position_opened_on_the_last_bar_closes_at_its_close():
    # Bar 10's signal buys 100 on bar 11 at its open of 102, then sells at its close of 103.
    result = simulate(TWELVE_BARS, at(12, 10), None, BacktestConfig(initial_capital=10_200))

    assert result.trades == [
        SimulatedTrade(
            direction=Direction.LONG,
            entry_time=TIMES[11],
            entry_price=102,
            exit_time=TIMES[11],
            exit_price=103,
            size=100,
            entry_fee=0,
            exit_fee=0,
            slippage=0,
            pnl=100,
            pnl_pct=approx(100 / 10_200 * 100),
            exit_reason=ExitReason.END_OF_DATA,
        )
    ]
    assert result.equity.tolist() == [10_200] * 11 + [10_300]


def test_closing_at_the_end_pays_slippage_and_fees():
    # As in the fees and slippage test, 100 are bought at 101 for a fee of 101. They are sold
    # at bar 11's close of 103 less 1%, 101.97, for a fee of 101.97.
    config = BacktestConfig(initial_capital=10_201, fee_pct=1, slippage_pct=1)

    result = simulate(TWELVE_BARS, at(12, 1), None, config)

    [trade] = result.trades
    assert trade.exit_price == approx(101.97)
    assert trade.exit_fee == approx(101.97)
    assert trade.slippage == approx(100 * (101 - 100) + 100 * (103 - 101.97))
    assert trade.pnl == approx(100 * (101.97 - 101) - 101 - 101.97)  # -105.97
    closes = TWELVE_BARS["close"].tolist()
    assert result.equity.tolist() == approx(
        [10_201, 10_201] + [100 * close for close in closes[2:11]] + [10_201 - 105.97]
    )


def test_fees_and_slippage_by_hand():
    # 1% fee and 1% slippage. Buying at bar 2's open of 100 pays 101; the 10,201 committed
    # covers a notional of 10,100 plus its 101 fee, so the size is 100. Selling at bar 5's
    # open of 110 gets 108.9, and the fee on that is 108.9.
    result = simulate(
        TWELVE_BARS,
        entries=at(12, 1),
        exits=at(12, 4),
        config=BacktestConfig(initial_capital=10_201, fee_pct=1, slippage_pct=1),
    )

    assert result.trades == [
        SimulatedTrade(
            direction=Direction.LONG,
            entry_time=TIMES[2],
            entry_price=approx(101),
            exit_time=TIMES[5],
            exit_price=approx(108.9),
            size=approx(100),
            entry_fee=approx(101),
            exit_fee=approx(108.9),
            slippage=approx(100 * (101 - 100) + 100 * (110 - 108.9)),
            pnl=approx(100 * (108.9 - 101) - 101 - 108.9),  # 580.1
            pnl_pct=approx(580.1 / 10_100 * 100),
            exit_reason=ExitReason.SIGNAL,
        )
    ]
    # While held: 10,201 - 101 + 100 * (close - 101), which is 100 * close.
    assert result.equity.tolist() == approx(
        [10_201, 10_201, 10_400, 10_600, 10_800] + [10_781.1] * 7
    )


@pytest.mark.parametrize("direction", list(Direction))
def test_pnl_agrees_with_live_trades(direction):
    bars = random_bars()
    rng = np.random.default_rng(1)
    config = BacktestConfig(10_000, position_size_pct=80, fee_pct=0.1, slippage_pct=0.05)

    result = simulate(bars, rng.random(300) < 0.1, rng.random(300) < 0.1, config, direction)

    assert len(result.trades) > 5
    for trade in result.trades:
        live = trade_pnl(
            direction,
            Decimal(trade.entry_price),
            Decimal(trade.size),
            Decimal(trade.exit_price),
            entry_fee=Decimal(trade.entry_fee),
            exit_fee=Decimal(trade.exit_fee),
        )
        assert trade.pnl == pytest.approx(float(live.amount), abs=1e-9)
        assert trade.pnl_pct == pytest.approx(float(live.pct), abs=1e-4)


# fmt: off
FALLING_BARS = bars_from([
    # open, high, low, close
    (100, 101,  99, 100),  # 0
    (100, 101,  98,  99),  # 1  entry signal
    (100, 101,  95,  96),  # 2  sell 100 @ 99 (100 less 1% slippage)
    ( 96,  97,  90,  91),  # 3
    ( 91,  92,  88,  90),  # 4  exit signal
    ( 90,  93,  89,  92),  # 5  buy back 100 @ 90.9 (90 plus 1% slippage)
    ( 92,  93,  91,  92),  # 6
])
# fmt: on


def test_a_short_by_hand():
    # 1% fee and 1% slippage. The 9,999 committed covers a notional of 9,900 plus its 99 fee,
    # so selling at 99 makes the size 100. Buying back at 90.9 costs a fee of 90.9.
    result = simulate(
        FALLING_BARS,
        entries=at(7, 1),
        exits=at(7, 4),
        config=BacktestConfig(initial_capital=9_999, fee_pct=1, slippage_pct=1),
        direction=Direction.SHORT,
    )

    assert result.trades == [
        SimulatedTrade(
            direction=Direction.SHORT,
            entry_time=FALLING_BARS.index[2],
            entry_price=approx(99),
            exit_time=FALLING_BARS.index[5],
            exit_price=approx(90.9),
            size=approx(100),
            entry_fee=approx(99),
            exit_fee=approx(90.9),
            slippage=approx(100 * (100 - 99) + 100 * (90.9 - 90)),
            pnl=approx(100 * (99 - 90.9) - 99 - 90.9),  # 620.1
            pnl_pct=approx(620.1 / 9_900 * 100),
            exit_reason=ExitReason.SIGNAL,
        )
    ]
    # While held: 9,999 - 99 - 100 * (close - 99), which is 19,800 - 100 * close.
    assert result.equity.tolist() == approx(
        [9_999, 9_999, 10_200, 10_700, 10_800, 10_619.1, 10_619.1]
    )


# fmt: off
RALLY_BARS = bars_from([
    # open, high, low, close
    (100, 101,  99, 100),  # 0  entry signal
    (100, 160,  99, 150),  # 1  sell 100 @ 100 with all 10,000
    (150, 210, 149, 200),  # 2  exit signal
    (250, 260, 240, 250),  # 3  buy back @ 250: -15,000; entry signal ignored: equity is gone
    (250, 251, 249, 250),  # 4  entry signal ignored
    (250, 251, 249, 250),  # 5
])
# fmt: on


def test_no_new_position_once_equity_is_gone():
    result = simulate(
        RALLY_BARS,
        entries=at(6, 0, 3, 4),
        exits=at(6, 2),
        config=BacktestConfig(initial_capital=10_000),
        direction=Direction.SHORT,
    )

    assert [trade.pnl for trade in result.trades] == [-15_000]
    assert result.equity.tolist() == [10_000, 5_000, 0, -5_000, -5_000, -5_000]


def run_from_bar_0(rows, *, capital=10_100, direction=Direction.LONG, exits=None, **levels):
    """An entry signal on bar 0, with 1% slippage."""
    bars = bars_from(rows)
    config = BacktestConfig(initial_capital=capital, slippage_pct=1)
    return bars, simulate(bars, at(len(bars), 0), exits, config, direction, **levels)


def run_with_stop(rows, **kwargs):
    """An entry signal on bar 0, with 1% slippage and a 10% stop-loss."""
    return run_from_bar_0(rows, stop_loss_pct=10, **kwargs)


# In the long stop-loss tests, bar 0's signal buys on bar 1 at its open of 100 plus 1%
# slippage, 101, with all of 10,100, so 100 units, and the 10% stop is at 90.9.


def test_a_stop_loss_reached_within_a_bar_fills_at_the_stop():
    # fmt: off
    bars, result = run_with_stop([
        (100, 101,  99, 100),
        (100, 103,  98, 102),  # the low of 98 stays above the stop
        (101, 103,  90,  92),  # the low of 90 reaches it: sell at 90.9 less 1%
        ( 92,  93,  91,  92),
    ])
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[2], ExitReason.STOP_LOSS)
    assert trade.exit_price == approx(90.9 * 0.99)
    assert trade.pnl == approx(100 * (90.9 * 0.99 - 101))  # -1,100.9
    assert result.equity.tolist() == approx([10_100, 10_200, 8_999.1, 8_999.1])


def test_a_gap_past_the_stop_fills_at_the_open():
    # fmt: off
    bars, result = run_with_stop([
        (100, 101,  99, 100),
        (100, 103,  98, 102),
        ( 88,  89,  85,  86),  # opens below the stop: sell at the open of 88 less 1%
        ( 86,  87,  85,  86),
    ])
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[2], ExitReason.STOP_LOSS)
    assert trade.exit_price == approx(88 * 0.99)


def test_a_stop_loss_can_be_reached_on_the_entry_bar():
    # fmt: off
    bars, result = run_with_stop([
        (100, 101,  99, 100),
        (100, 101,  89,  95),  # buys at the open, then the low of 89 reaches the stop
        ( 95,  96,  94,  95),
    ])
    # fmt: on

    [trade] = result.trades
    assert trade.entry_time == trade.exit_time == bars.index[1]
    assert trade.exit_reason == ExitReason.STOP_LOSS
    assert trade.exit_price == approx(90.9 * 0.99)


def test_a_pending_exit_signal_fills_at_the_open_before_the_stop():
    # fmt: off
    bars, result = run_with_stop([
        (100, 101,  99, 100),
        (100, 103,  98, 102),  # exit signal
        (101, 103,  90,  92),  # sells at the open; the low reaching the stop comes later
        ( 92,  93,  91,  92),
    ], exits=at(4, 1))
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[2], ExitReason.SIGNAL)
    assert trade.exit_price == approx(101 * 0.99)


def test_an_entry_signal_on_the_stop_bar_reenters_on_the_next_bar():
    # fmt: off
    bars = bars_from([
        (100, 101,  99, 100),  # entry signal
        (100, 103,  98, 102),
        (101, 103,  90,  92),  # stopped out; entry signal
        ( 92,  93,  91,  92),  # buys again
        ( 92,  93,  91,  92),
    ])
    # fmt: on
    config = BacktestConfig(initial_capital=10_100, slippage_pct=1)

    result = simulate(bars, at(5, 0, 2), None, config, stop_loss_pct=10)

    assert [(trade.entry_time, trade.exit_reason) for trade in result.trades] == [
        (bars.index[1], ExitReason.STOP_LOSS),
        (bars.index[3], ExitReason.END_OF_DATA),
    ]


# In the short stop-loss tests, bar 0's signal sells on bar 1 at its open of 100 less 1%
# slippage, 99, with all of 9,900, so 100 units, and the 10% stop is at 108.9.


def test_a_short_stop_loss_is_reached_by_the_high():
    # fmt: off
    bars, result = run_with_stop([
        (100, 101,  99, 100),
        (100, 102,  97,  98),  # the high of 102 stays below the stop
        ( 99, 110,  98, 105),  # the high of 110 reaches it: buy back at 108.9 plus 1%
        (105, 106, 104, 105),
    ], capital=9_900, direction=Direction.SHORT)
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[2], ExitReason.STOP_LOSS)
    assert trade.exit_price == approx(108.9 * 1.01)
    assert trade.pnl == approx(-100 * (108.9 * 1.01 - 99))


def test_a_short_gap_past_the_stop_fills_at_the_open():
    # fmt: off
    bars, result = run_with_stop([
        (100, 101,  99, 100),
        (100, 102,  97,  98),
        (112, 115, 111, 113),  # opens above the stop: buy back at the open of 112 plus 1%
        (113, 114, 112, 113),
    ], capital=9_900, direction=Direction.SHORT)
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[2], ExitReason.STOP_LOSS)
    assert trade.exit_price == approx(112 * 1.01)


@pytest.mark.parametrize("hit", [1, 16, 17, 48, 49, 1_500])
def test_a_stop_loss_is_found_however_far_from_the_entry(hit):
    # Flat bars except one whose low reaches the stop. Hits on both sides of the scan's chunk
    # boundaries (it scans 16 bars from the entry on bar 1, then 32, 64, ...).
    rows = [(100, 101, 99, 100)] * 2_000
    rows[hit] = (100, 101, 80, 100)
    bars = bars_from(rows)

    result = simulate(bars, at(2_000, 0), None, BacktestConfig(10_000), stop_loss_pct=10)

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[hit], ExitReason.STOP_LOSS)
    assert trade.exit_price == approx(90)


# In the long take-profit tests, bar 0's signal buys on bar 1 at its open of 100 plus 1%
# slippage, 101, with all of 10,100, so 100 units. A 10% target is at 111.1 (and a 10% stop
# at 90.9).


def test_a_take_profit_fills_at_the_target_without_slippage():
    # fmt: off
    bars, result = run_from_bar_0([
        (100, 101,  99, 100),
        (100, 105,  99, 104),  # the high of 105 stays below the target
        (105, 112, 104, 110),  # the high of 112 reaches it: sell at exactly 111.1
        (110, 111, 109, 110),
    ], take_profit_pct=10)
    # fmt: on

    assert result.trades == [
        SimulatedTrade(
            direction=Direction.LONG,
            entry_time=bars.index[1],
            entry_price=approx(101),
            exit_time=bars.index[2],
            exit_price=approx(111.1),
            size=approx(100),
            entry_fee=0,
            exit_fee=0,
            slippage=approx(100 * (101 - 100)),  # on the entry only
            pnl=approx(100 * (111.1 - 101)),  # 1,010
            pnl_pct=approx(1_010 / 10_100 * 100),
            exit_reason=ExitReason.TAKE_PROFIT,
        )
    ]
    assert result.equity.tolist() == approx([10_100, 10_400, 11_110, 11_110])


def test_a_gap_past_the_target_fills_at_the_better_open():
    # fmt: off
    bars, result = run_from_bar_0([
        (100, 101,  99, 100),
        (100, 105,  99, 104),
        (115, 116, 113, 114),  # opens above the target: sell at the open of 115
        (114, 115, 113, 114),
    ], take_profit_pct=10)
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[2], ExitReason.TAKE_PROFIT)
    assert trade.exit_price == 115


def test_when_a_bar_reaches_both_the_stop_loss_counts():
    # fmt: off
    bars, result = run_from_bar_0([
        (100, 101,  99, 100),
        (100, 105,  99, 104),
        (101, 112,  90, 100),  # the high of 112 reaches the target, the low of 90 the stop
        (100, 101,  99, 100),
    ], stop_loss_pct=10, take_profit_pct=10)
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[2], ExitReason.STOP_LOSS)
    assert trade.exit_price == approx(90.9 * 0.99)


def test_the_first_level_reached_counts():
    # fmt: off
    bars, result = run_from_bar_0([
        (100, 101,  99, 100),
        (100, 112,  99, 110),  # the high of 112 reaches the target first
        (110, 111,  80,  85),  # the stop would be reached here
    ], stop_loss_pct=10, take_profit_pct=10)
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[1], ExitReason.TAKE_PROFIT)


# In the short take-profit tests, bar 0's signal sells on bar 1 at its open of 100 less 1%
# slippage, 99, with all of 9,900, so 100 units. A 10% target is at 89.1 (and a 10% stop at
# 108.9).


def test_a_short_take_profit_is_reached_by_the_low():
    # fmt: off
    bars, result = run_from_bar_0([
        (100, 101,  99, 100),
        (100, 101,  95,  96),  # the low of 95 stays above the target
        ( 95,  96,  88,  90),  # the low of 88 reaches it: buy back at exactly 89.1
        ( 90,  91,  89,  90),
    ], capital=9_900, direction=Direction.SHORT, take_profit_pct=10)
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[2], ExitReason.TAKE_PROFIT)
    assert trade.exit_price == approx(89.1)
    assert trade.pnl == approx(100 * (99 - 89.1))  # 990


def test_a_short_gap_past_the_target_fills_at_the_better_open():
    # fmt: off
    bars, result = run_from_bar_0([
        (100, 101,  99, 100),
        (100, 101,  95,  96),
        ( 85,  86,  84,  85),  # opens below the target: buy back at the open of 85
        ( 85,  86,  84,  85),
    ], capital=9_900, direction=Direction.SHORT, take_profit_pct=10)
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[2], ExitReason.TAKE_PROFIT)
    assert trade.exit_price == 85


def test_when_a_bar_reaches_both_a_short_stop_loss_counts():
    # fmt: off
    bars, result = run_from_bar_0([
        (100, 101,  99, 100),
        (100, 101,  95,  96),
        ( 99, 110,  88, 100),  # the low of 88 reaches the target, the high of 110 the stop
        (100, 101,  99, 100),
    ], capital=9_900, direction=Direction.SHORT, stop_loss_pct=10, take_profit_pct=10)
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[2], ExitReason.STOP_LOSS)
    assert trade.exit_price == approx(108.9 * 1.01)


def run_with_levels(rows, stop_loss, take_profit=None, *, direction=Direction.LONG, entries=(0,)):
    """Signals on the given bars (bar 0 by default), all of 10,000, no costs."""
    bars = bars_from(rows)
    orders = Orders(direction, at(len(bars), *entries), None, stop_loss, take_profit)
    return bars, simulate_orders(bars, orders, BacktestConfig(initial_capital=10_000))


def level(price: float, length: int = 5, unknown: tuple[int, ...] = ()) -> Level:
    """A price level of `price` on every bar, except the `unknown` ones."""
    prices = np.full(length, float(price))
    prices[list(unknown)] = np.nan
    return Level(at=prices)


# In the level tests, bar 0's signal buys 100 @ 100 on bar 1, with a stop-loss at a level of
# 95 read on bar 0: 5 below the entry.


def test_a_stop_loss_at_a_level_fills_there():
    # fmt: off
    bars, result = run_with_levels([
        (100, 101,  99, 100),
        (100, 104,  98, 103),
        (103, 104,  94,  96),  # the low of 94 reaches 95
        ( 96,  97,  95,  96),
        ( 96,  97,  95,  96),
    ], level(95))
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[2], ExitReason.STOP_LOSS)
    assert (trade.exit_price, trade.pnl) == (95, -500)


def test_a_take_profit_at_twice_the_risk():
    # fmt: off
    bars, result = run_with_levels([
        (100, 101,  99, 100),
        (100, 104,  98, 103),
        (103, 108, 101, 107),
        (107, 111, 106, 110),  # 2R is 100 + 2 * 5 = 110, reached by the high of 111
        (110, 112, 109, 111),
    ], level(95), Level(r=2))
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[3], ExitReason.TAKE_PROFIT)
    assert (trade.exit_price, trade.pnl) == (110, 1_000)


def test_a_take_profit_at_a_level():
    # fmt: off
    bars, result = run_with_levels([
        (100, 101,  99, 100),
        (100, 104,  98, 103),
        (103, 108, 101, 107),  # the high of 108 reaches 106
        (107, 111, 106, 110),
        (110, 112, 109, 111),
    ], level(95), level(106))
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[2], ExitReason.TAKE_PROFIT)
    assert trade.exit_price == 106


def test_a_stop_loss_already_passed_exits_at_the_entry_open():
    # A stop at 101 is above the entry of 100: reached as soon as the position opens.
    bars, result = run_with_levels([(100, 101, 99, 100)] * 5, level(101))

    [trade] = result.trades
    assert (trade.entry_time, trade.exit_time) == (bars.index[1], bars.index[1])
    assert (trade.exit_price, trade.exit_reason, trade.pnl) == (100, ExitReason.STOP_LOSS, 0)


def test_a_signal_whose_level_is_unknown_places_no_order():
    # fmt: off
    bars, result = run_with_levels([
        (100, 101,  99, 100),  # signal, but no stop level yet
        (100, 104,  98, 103),  # signal
        (103, 108, 101, 107),  # buy
        (107, 111, 106, 110),
        (110, 112, 109, 111),
    ], level(95, unknown=(0,)), entries=(0, 1))
    # fmt: on

    [trade] = result.trades
    assert (trade.entry_time, trade.entry_price) == (bars.index[2], 103)


def test_a_short_stop_and_target_at_levels():
    # fmt: off
    bars, result = run_with_levels([
        (100, 101,  99, 100),
        (100, 102,  97,  98),
        ( 98,  99,  94,  95),  # 1R below the entry of 100 is 95, reached by the low of 94
        ( 95,  96,  94,  95),
        ( 95,  96,  94,  95),
    ], level(105), Level(r=1), direction=Direction.SHORT)
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[2], ExitReason.TAKE_PROFIT)
    assert (trade.exit_price, trade.pnl) == (95, 500)


def run_entry(
    rows,
    kind,
    price,
    *,
    direction=Direction.LONG,
    entries=(0,),
    expires_after=1,
    stop_loss=None,
    take_profit=None,
    slippage_pct=0,
):
    """Signals on the given bars (bar 0 by default) placing `kind` orders at `price` (one price,
    or one per bar), with all of 10,000."""
    bars = bars_from(rows)
    length = len(bars)
    prices = price if isinstance(price, np.ndarray) else np.full(length, float(price))
    entry = Entry(kind, prices, expires_after)
    orders = Orders(direction, at(length, *entries), None, stop_loss, take_profit, entry)
    config = BacktestConfig(initial_capital=10_000, slippage_pct=slippage_pct)
    return bars, simulate_orders(bars, orders, config)


def test_a_limit_order_fills_at_its_price_without_slippage():
    # fmt: off
    bars, result = run_entry([
        (100, 101,  99, 100),  # buy at 98 or better
        (100, 101,  97,  99),  # the low of 97 reaches it
        ( 99, 100,  98,  99),
    ], "limit", 98, slippage_pct=1)
    # fmt: on

    [trade] = result.trades
    assert (trade.entry_time, trade.entry_price) == (bars.index[1], 98)


def test_a_limit_order_fills_at_a_better_open():
    bars, result = run_entry([(100, 101, 99, 100), (96, 99, 95, 98), (98, 99, 97, 98)], "limit", 98)

    [trade] = result.trades
    assert (trade.entry_time, trade.entry_price) == (bars.index[1], 96)


# fmt: off
REACHES_95_ON_BAR_3 = [
    (100, 101, 99, 100),
    (100, 101, 96,  99),
    ( 99, 100, 96,  99),
    ( 99, 100, 94,  95),
    ( 95,  96, 94,  95),
]
# fmt: on


def test_a_limit_order_works_until_it_expires():
    _, expired = run_entry(REACHES_95_ON_BAR_3, "limit", 95, expires_after=2)
    bars, working = run_entry(REACHES_95_ON_BAR_3, "limit", 95, expires_after=3)

    assert expired.trades == []
    [trade] = working.trades
    assert (trade.entry_time, trade.entry_price) == (bars.index[3], 95)


def test_a_newer_signal_replaces_the_order_and_sets_the_levels():
    # fmt: off
    bars, result = run_entry([
        (100, 101, 99,   100),  # signal: buy at 95, stop at 90
        (100, 101, 96,    99),  # signal: buy at 97, stop at 92 (95 isn't reached)
        ( 99, 100, 96.5,  98),  # 97 is reached
        ( 98,  99, 91,    92),  # the stop at 92 is reached
        ( 92,  93, 91,    92),
    ], "limit", np.array([95, 97, 97, 97, 97.0]), entries=(0, 1),
       stop_loss=Level(at=np.array([90, 92, 92, 92, 92.0])))
    # fmt: on

    [trade] = result.trades
    assert (trade.entry_time, trade.entry_price) == (bars.index[2], 97)
    assert (trade.exit_time, trade.exit_price) == (bars.index[3], 92)


def test_a_stop_order_fills_once_price_trades_through_it_with_slippage():
    _, inside = run_entry(
        [(100, 101, 99, 100), (100, 103, 99, 102.5), (102, 103, 101, 102)],
        "stop",
        102,
        slippage_pct=1,
    )
    _, gap = run_entry(
        [(100, 101, 99, 100), (104, 105, 103, 104.5), (104, 105, 103, 104)],
        "stop",
        102,
        slippage_pct=1,
    )

    [trade] = inside.trades
    assert trade.entry_price == approx(102 * 1.01)
    # Slippage is measured from the order's price, not the bar's open: 1.02 on the way in
    # and 1.02 on the way out at the last close of 102.
    assert trade.slippage == approx(trade.size * (1.02 + 1.02))
    assert gap.trades[0].entry_price == approx(104 * 1.01)  # it opened above 102


def test_a_stop_loss_reached_on_the_fill_bar_counts():
    # fmt: off
    bars, result = run_entry([
        (100, 101, 99, 100),
        (100, 101, 95,  97),  # buys at 98, and the low of 95 reaches the stop at 96
        ( 97,  98, 96,  97),
    ], "limit", 98, stop_loss=level(96, length=3))
    # fmt: on

    [trade] = result.trades
    assert trade.entry_time == trade.exit_time == bars.index[1]
    assert (trade.exit_price, trade.exit_reason) == (96, ExitReason.STOP_LOSS)


def test_a_stop_loss_already_passed_at_an_inside_fill_exits_at_the_fill_price():
    # The stop at 99 is above the fill at 98: the position is stopped as soon as it opens.
    bars, result = run_entry(
        [(100, 101, 99, 100), (100, 101, 97, 99), (99, 100, 98, 99)],
        "limit",
        98,
        stop_loss=level(99, length=3),
    )

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_price, trade.pnl) == (bars.index[1], 98, 0)


def test_no_take_profit_on_the_bar_of_an_inside_fill():
    # fmt: off
    bars, result = run_entry([
        (100, 101,  99, 100),
        (100, 110,  97, 104),  # buys at 98; the high of 110 may have come first
        (104, 106, 103, 105),  # the target at 105 is reached
    ], "limit", 98, take_profit=level(105, length=3))
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_price) == (bars.index[2], 105)


def test_a_take_profit_counts_on_the_bar_of_a_fill_at_the_open():
    # fmt: off
    bars, result = run_entry([
        (100, 101,  99, 100),
        ( 97, 106,  96, 105),  # opens below 98: buys at 97, then the high reaches 105
        (105, 106, 104, 105),
    ], "limit", 98, take_profit=level(105, length=3))
    # fmt: on

    [trade] = result.trades
    assert (trade.entry_price, trade.exit_time, trade.exit_price) == (97, bars.index[1], 105)


def test_short_limit_and_stop_orders():
    _, limit = run_entry(
        [(100, 101, 99, 100), (100, 103, 99, 101), (101, 102, 100, 101)],
        "limit",
        102,
        direction=Direction.SHORT,
    )
    _, stop = run_entry(
        [(100, 101, 99, 100), (100, 101, 97, 98.5), (98, 99, 97, 98)],
        "stop",
        98,
        direction=Direction.SHORT,
        slippage_pct=1,
    )

    # A short limit sells at 102 or higher; a short stop sells once price falls through 98.
    assert limit.trades[0].entry_price == 102
    assert stop.trades[0].entry_price == approx(98 * 0.99)


def test_a_signal_whose_order_price_is_unknown_places_no_order():
    # fmt: off
    bars, result = run_entry([
        (100, 101, 99,   100),  # signal, but no price yet
        (100, 101, 96,    99),  # signal; nothing is working on this bar
        ( 99, 100, 96.5,  98),  # 97 is reached
    ], "limit", np.array([np.nan, 97, 97]), entries=(0, 1))
    # fmt: on

    [trade] = result.trades
    assert (trade.entry_time, trade.entry_price) == (bars.index[2], 97)


def run_trailing(rows, trailing_stop, *, stop_loss=None, direction=Direction.LONG):
    """A signal on bar 0, with all of 10,000 and no costs: 100 units at 100 on bar 1."""
    bars = bars_from(rows)
    orders = Orders(direction, at(len(bars), 0), None, stop_loss, None, trailing_stop=trailing_stop)
    return bars, simulate_orders(bars, orders, BacktestConfig(initial_capital=10_000))


def test_a_trailing_stop_follows_the_best_price():
    # fmt: off
    bars, result = run_trailing([
        (100, 101,  99, 100),
        (100, 105,  99, 104),  # 10% behind the entry of 100: 90
        (104, 110, 103, 109),  # behind the high of 105 so far: 94.5
        (109, 111,  98, 100),  # behind the high of 110: 99, reached by the low of 98
        (100, 101,  97,  98),
    ], Level(pct=10))
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[3], ExitReason.TRAILING_STOP)
    assert trade.exit_price == approx(99)


def test_a_trailing_level_applies_from_the_next_bar():
    # Levels read on each close: bar 2's 104 would stop the trade on bar 2 itself, whose low is
    # 101, if it applied there; it applies from bar 3.
    levels = np.array([90, 92, 104, 91, 91.0])
    # fmt: off
    bars, result = run_trailing([
        (100, 101,  99, 100),
        (100, 103,  99, 102),  # level 90
        (102, 106, 101, 105),  # level 92
        (105, 106, 103, 104),  # level 104, reached by the low of 103
        (104, 105, 103, 104),
    ], Level(at=levels))
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[3], ExitReason.TRAILING_STOP)
    assert trade.exit_price == 104


def test_a_trailing_level_never_loosens():
    # Bar 2's close reads 91, below the 92 already reached: the stop stays at 92.
    levels = np.array([90, 92, 91, 91, 91.0])
    # fmt: off
    bars, result = run_trailing([
        (100, 101, 99,   100),
        (100, 101, 95,    96),
        ( 96,  97, 93,    96),
        ( 96,  97, 91.5,  94),  # reaches 92, not 91
        ( 94,  95, 93,    94),
    ], Level(at=levels))
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_price) == (bars.index[3], 92)


# fmt: off
RISES_THEN_FALLS = [
    (100, 101, 99, 100),
    (100, 101, 97, 100),  # the fixed stop at 95 is tighter than the trailing one at 90
    (100, 110, 99, 109),
    (109, 110, 96, 98),   # now the trailing stop is at 99, above 95
    ( 98,  99, 94, 95),
]
# fmt: on


def test_the_tighter_of_the_fixed_and_trailing_stops_counts():
    bars, result = run_trailing(RISES_THEN_FALLS, Level(pct=10), stop_loss=Level(pct=5))
    _, falls_first = run_trailing(
        [RISES_THEN_FALLS[0], (100, 101, 94, 96)], Level(pct=10), stop_loss=Level(pct=5)
    )

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason, trade.exit_price) == (
        bars.index[3],
        ExitReason.TRAILING_STOP,
        approx(99),
    )
    [early] = falls_first.trades
    assert (early.exit_reason, early.exit_price) == (ExitReason.STOP_LOSS, 95)


def test_a_short_trailing_stop_follows_the_lows():
    # fmt: off
    bars, result = run_trailing([
        (100, 101,  99, 100),
        (100, 101,  95,  96),  # 10% above the entry of 100: 110
        ( 96,  97,  90,  91),  # above the low of 95 so far: 104.5
        ( 91, 100,  90,  99),  # above the low of 90: 99, reached by the high of 100
        ( 99, 100,  98,  99),
    ], Level(pct=10), direction=Direction.SHORT)
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[3], ExitReason.TRAILING_STOP)
    assert trade.exit_price == approx(99)


def test_a_trailing_stop_does_not_count_the_high_before_an_inside_fill():
    # The limit buys at 98 inside bar 1, whose high of 104 may have come first: the stop
    # trails the fill price, 88.2, not 104 (93.6), and the low of 90 on bar 2 doesn't reach it.
    bars = bars_from([(100, 101, 99, 100), (100, 104, 97, 99), (99, 100, 90, 95), (95, 96, 94, 95)])
    entry = Entry("limit", np.full(4, 98.0))
    orders = Orders(Direction.LONG, at(4, 0), None, None, None, entry, Level(pct=10))

    result = simulate_orders(bars, orders, BacktestConfig(initial_capital=10_000))

    [trade] = result.trades
    assert (trade.entry_price, trade.exit_reason) == (98, ExitReason.END_OF_DATA)


def run_timed(rows, exit_after_bars, *, exits=None, stop_loss=None):
    """A signal on bar 0, with all of 10,000 and no costs: 100 units at 100 on bar 1."""
    bars = bars_from(rows)
    orders = Orders(
        Direction.LONG, at(len(bars), 0), exits, stop_loss, exit_after_bars=exit_after_bars
    )
    return bars, simulate_orders(bars, orders, BacktestConfig(initial_capital=10_000))


# fmt: off
FIVE_FLAT_BARS = [
    (100, 101, 99, 100),
    (100, 101, 99, 100),  # buy
    (101, 102, 100, 101),
    (102, 103, 101, 102),
    (103, 104, 102, 103),
]
# fmt: on


def test_a_time_exit_leaves_at_the_open_after_so_many_bars():
    bars, result = run_timed(FIVE_FLAT_BARS, 2)

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_price) == (bars.index[3], 102)
    assert trade.exit_reason == ExitReason.TIME_EXIT


def test_an_earlier_signal_exit_comes_first():
    bars, result = run_timed(FIVE_FLAT_BARS, 3, exits=at(5, 1))

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[2], ExitReason.SIGNAL)


def test_a_signal_exit_on_the_same_bar_counts_as_the_signal():
    bars, result = run_timed(FIVE_FLAT_BARS, 2, exits=at(5, 2))

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[3], ExitReason.SIGNAL)


def test_a_time_exit_at_the_open_comes_before_a_stop_on_that_bar():
    rows = [*FIVE_FLAT_BARS[:3], (102, 103, 80, 85), (85, 86, 84, 85)]

    bars, result = run_timed(rows, 2, stop_loss=Level(pct=10))

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_price) == (bars.index[3], 102)
    assert trade.exit_reason == ExitReason.TIME_EXIT


def test_a_time_exit_beyond_the_data_closes_at_the_end():
    bars, result = run_timed(FIVE_FLAT_BARS, 10)

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_reason) == (bars.index[4], ExitReason.END_OF_DATA)


def hourly(rows) -> pd.DataFrame:
    bars = bars_from(rows)
    bars.index = pd.date_range(ENTRY_TIME, periods=len(rows), freq="h")
    return bars


def detail_of(bars: pd.DataFrame, inside: dict[int, list[tuple]]) -> Detail:
    """Finer bars inside the given hourly bars, spread evenly over each hour."""
    parts = []
    for bar, rows in inside.items():
        part = pd.DataFrame(rows, columns=["open", "high", "low", "close"], dtype=float)
        step = pd.Timedelta(hours=1) / len(rows)
        part.index = pd.date_range(bars.index[bar], periods=len(rows), freq=step)
        parts.append(part)
    return Detail(pd.concat(parts).sort_index(), pd.Timedelta(hours=1))


# Bar 0's signal buys 100 @ 100 on bar 1, with a 5% stop at 95 and a 5% target at 105; bar 2
# reaches both.
# fmt: off
BOTH_ON_BAR_2 = hourly([
    (100, 101, 99, 100),
    (100, 101, 99, 100),
    (100, 106, 94, 100),
    (100, 101, 99, 100),
])
# fmt: on
BRACKET = Orders(Direction.LONG, at(4, 0), None, Level(pct=5), Level(pct=5))


def test_finer_bars_say_which_level_came_first():
    # fmt: off
    target_first = detail_of(BOTH_ON_BAR_2, {2: [
        (100, 106, 99, 105),
        (105, 105, 94, 95),
        ( 95, 101, 95, 100),
    ]})
    stop_first = detail_of(BOTH_ON_BAR_2, {2: [
        (100, 101, 94, 95),
        ( 95, 106, 95, 105),
        (105, 105, 99, 100),
    ]})
    # fmt: on
    config = BacktestConfig(initial_capital=10_000)

    [up] = simulate_orders(BOTH_ON_BAR_2, BRACKET, config, target_first).trades
    [down] = simulate_orders(BOTH_ON_BAR_2, BRACKET, config, stop_first).trades
    [unknown] = simulate_orders(BOTH_ON_BAR_2, BRACKET, config).trades

    assert (up.exit_reason, up.exit_price) == (ExitReason.TAKE_PROFIT, 105)
    assert (down.exit_reason, down.exit_price) == (ExitReason.STOP_LOSS, 95)
    assert (unknown.exit_reason, unknown.exit_price) == (ExitReason.STOP_LOSS, 95)
    assert up.exit_time == down.exit_time == BOTH_ON_BAR_2.index[2]


def test_missing_or_inconsistent_finer_bars_leave_the_worst_case():
    config = BacktestConfig(initial_capital=10_000)
    elsewhere = detail_of(BOTH_ON_BAR_2, {1: [(100, 101, 99, 100)]})
    # Finer bars that reach neither level, unlike their bar.
    inconsistent = detail_of(BOTH_ON_BAR_2, {2: [(100, 101, 99, 100), (100, 101, 99, 100)]})

    for detail in (elsewhere, inconsistent):
        [trade] = simulate_orders(BOTH_ON_BAR_2, BRACKET, config, detail).trades
        assert (trade.exit_reason, trade.exit_price) == (ExitReason.STOP_LOSS, 95)


def limit_at_98(rows, inside, **levels):
    """Bar 0's signal places a limit order at 98, for 10,000 with no costs."""
    bars = hourly(rows)
    entry = Entry("limit", np.full(len(bars), 98.0))
    orders = Orders(Direction.LONG, at(len(bars), 0), None, entry=entry, **levels)
    detail = detail_of(bars, inside)
    return bars, simulate_orders(bars, orders, BacktestConfig(initial_capital=10_000), detail)


def test_finer_bars_let_a_take_profit_count_after_an_inside_fill():
    # Without finer bars, the target on the fill's bar wouldn't count (it may have come first).
    # fmt: off
    bars, result = limit_at_98([
        (100, 101,  99, 100),
        (100, 110,  97, 104),
        (104, 106, 103, 105),
    ], {1: [
        (100, 100,  97,  98),  # buys at 98
        ( 98, 106,  98, 105),  # then reaches 105
        (105, 110, 103, 104),
    ]}, take_profit=Level(at=np.full(3, 105.0)))
    # fmt: on

    [trade] = result.trades
    assert (trade.entry_price, trade.exit_time, trade.exit_price) == (98, bars.index[1], 105)
    assert trade.exit_reason == ExitReason.TAKE_PROFIT


def test_finer_bars_fill_an_order_at_a_gap_past_it():
    # fmt: off
    bars, result = limit_at_98([
        (100, 101,  99, 100),
        (100, 101,  95,  96),
        ( 96,  97,  95,  96),
    ], {1: [
        (100, 101,  99,  99),
        ( 96,  97,  95,  96),  # opens below 98: buys at 96
    ]})
    # fmt: on

    [trade] = result.trades
    assert (trade.entry_time, trade.entry_price) == (bars.index[1], 96)


def test_finer_bars_stop_a_trade_after_an_inside_fill():
    # fmt: off
    bars, result = limit_at_98([
        (100, 101,  99, 100),
        (100, 101,  95,  96),
        ( 96,  97,  95,  96),
    ], {1: [
        (100, 100,  97,  98),    # buys at 98; the stop at 96 isn't reached yet
        ( 98,  99,  95.5, 96),  # then it is
    ]}, stop_loss=Level(at=np.full(3, 96.0)))
    # fmt: on

    [trade] = result.trades
    assert (trade.exit_time, trade.exit_price) == (bars.index[1], 96)
    assert trade.exit_reason == ExitReason.STOP_LOSS


def test_run_passes_finer_bars_to_the_simulation():
    detail = detail_of(BOTH_ON_BAR_2, {2: [(100, 106, 99, 105), (105, 105, 94, 95)]})
    definition = StrategyDefinition.model_validate(
        {
            "direction": "long",
            "entry": {"left": {"price": "close"}, "op": "<=", "right": {"value": 100}},
            "stop_loss_pct": 5,
            "take_profit_pct": 5,
        }
    )
    config = BacktestConfig(initial_capital=10_000)

    [trade, *_] = run(BOTH_ON_BAR_2, definition, config, detail).trades

    assert (trade.exit_reason, trade.exit_price) == (ExitReason.TAKE_PROFIT, 105)


def rsi_strategy(direction: Direction) -> StrategyDefinition:
    """Trades RSI(5) swings, with a stop-loss and a take-profit, so that every kind of exit
    happens within a few hundred random bars."""
    return StrategyDefinition.model_validate(
        {
            "direction": direction,
            "entry": {"left": {"indicator": "rsi", "period": 5}, "op": "<", "right": {"value": 35}},
            "exit": {"left": {"indicator": "rsi", "period": 5}, "op": ">", "right": {"value": 60}},
            "stop_loss_pct": 3,
            "take_profit_pct": 4,
        }
    )


COSTS = BacktestConfig(initial_capital=10_000, position_size_pct=90, fee_pct=0.1, slippage_pct=0.05)


@pytest.mark.parametrize("direction", list(Direction))
def test_run_trades_the_definition(direction):
    bars = random_bars()
    definition = rsi_strategy(direction)

    result = run(bars, definition, COSTS)

    entries, exits = strategy_signals(definition, bars)
    expected = simulate(bars, entries, exits, COSTS, direction, stop_loss_pct=3, take_profit_pct=4)
    assert result.trades == expected.trades
    assert result.equity.equals(expected.equity)
    assert {trade.exit_reason for trade in result.trades} >= {
        ExitReason.SIGNAL,
        ExitReason.STOP_LOSS,
        ExitReason.TAKE_PROFIT,
    }


@pytest.mark.parametrize("direction", list(Direction))
def test_run_reads_levels_on_the_signal_bar(direction):
    bars = random_bars()
    definition = StrategyDefinition.model_validate(
        rsi_strategy(direction).model_dump()
        | {
            "stop_loss_pct": None,
            "stop_loss_at": {
                "indicator": "lowest" if direction == "long" else "highest",
                "period": 3,
            },
            "take_profit_pct": None,
            "take_profit_r": 2,
        }
    )

    result = run(bars, definition, COSTS)

    entries, exits = strategy_signals(definition, bars)
    extreme = (
        indicators.lowest(bars["low"], 3)
        if direction == "long"
        else indicators.highest(bars["high"], 3)
    )
    orders = Orders(direction, entries, exits, Level(at=extreme.to_numpy()), Level(r=2))
    assert result.trades == simulate_orders(bars, orders, COSTS).trades
    assert {trade.exit_reason for trade in result.trades} >= {
        ExitReason.STOP_LOSS,
        ExitReason.TAKE_PROFIT,
    }


@pytest.mark.parametrize("direction", list(Direction))
def test_run_places_entry_orders(direction):
    bars = random_bars()
    # A limit 0.5% better than the signal bar's close, working for 3 bars.
    better = 0.995 if direction == "long" else 1.005
    definition = StrategyDefinition.model_validate(
        rsi_strategy(direction).model_dump()
        | {
            "entry_order": {
                "type": "limit",
                "price": {"multiply": [{"price": "close"}, {"value": better}]},
                "expires_after": 3,
            }
        }
    )

    result = run(bars, definition, COSTS)

    entries, exits = strategy_signals(definition, bars)
    entry = Entry("limit", bars["close"].to_numpy() * better, 3)
    orders = Orders(direction, entries, exits, Level(pct=3), Level(pct=4), entry)
    assert result.trades == simulate_orders(bars, orders, COSTS).trades
    assert len(result.trades) > 5


@pytest.mark.parametrize("direction", list(Direction))
def test_run_trails_a_level(direction):
    bars = random_bars()
    # A chandelier exit: 3 ATRs behind the 22-bar extreme.
    extreme = (
        {"indicator": "highest", "period": 22}
        if direction == "long"
        else {"indicator": "lowest", "period": 22}
    )
    behind = "subtract" if direction == "long" else "add"
    definition = StrategyDefinition.model_validate(
        rsi_strategy(direction).model_dump()
        | {
            "exit": None,
            "stop_loss_pct": None,
            "take_profit_pct": None,
            "trailing_stop_at": {
                behind: [extreme, {"multiply": [{"indicator": "atr", "period": 22}, {"value": 3}]}]
            },
        }
    )

    result = run(bars, definition, COSTS)

    entries, _ = strategy_signals(definition, bars)
    atr = indicators.atr(bars["high"], bars["low"], bars["close"], 22)
    if direction == "long":
        levels = indicators.highest(bars["high"], 22) - 3 * atr
    else:
        levels = indicators.lowest(bars["low"], 22) + 3 * atr
    orders = Orders(direction, entries, None, trailing_stop=Level(at=levels.to_numpy()))
    assert result.trades == simulate_orders(bars, orders, COSTS).trades
    reasons = [trade.exit_reason for trade in result.trades]
    assert set(reasons) <= {ExitReason.TRAILING_STOP, ExitReason.END_OF_DATA}
    assert reasons.count(ExitReason.TRAILING_STOP) > 5


def test_run_exits_after_so_many_bars():
    bars = random_bars()
    definition = StrategyDefinition.model_validate(
        rsi_strategy(Direction.LONG).model_dump() | {"exit": None, "exit_after_bars": 12}
    )

    result = run(bars, definition, COSTS)

    entries, _ = strategy_signals(definition, bars)
    orders = Orders(Direction.LONG, entries, None, Level(pct=3), Level(pct=4), exit_after_bars=12)
    assert result.trades == simulate_orders(bars, orders, COSTS).trades
    assert ExitReason.TIME_EXIT in {trade.exit_reason for trade in result.trades}


def every_order(direction: Direction) -> StrategyDefinition:
    """Every kind of order and exit, on a rule with every kind of event: a limit entry, a stop
    under a swing point, a target at twice the risk, a chandelier trailing stop and a time
    exit. Mirrored for shorts."""
    long = direction == Direction.LONG
    swing = "swing_low" if long else "swing_high"
    extreme, far = ("lowest", "highest") if long else ("highest", "lowest")
    behind = "subtract" if long else "add"
    atr = {"indicator": "atr", "period": 5}
    return StrategyDefinition.model_validate(
        {
            "direction": direction,
            "entry": {
                "all": [
                    {
                        "left": {"indicator": "rsi", "period": 5},
                        "op": "<" if long else ">",
                        "right": {"value": 45 if long else 55},
                    },
                    {
                        "happened": {
                            "left": {"price": "low" if long else "high"},
                            "op": "<=" if long else ">=",
                            "right": {"indicator": extreme, "period": 10, "bars_ago": 1},
                        },
                        "within": 5,
                    },
                ]
            },
            "entry_order": {
                "type": "limit",
                "price": {"multiply": [{"price": "close"}, {"value": 0.998 if long else 1.002}]},
                "expires_after": 3,
            },
            "stop_loss_at": {behind: [{"indicator": swing, "strength": 2}, atr]},
            "take_profit_r": 2,
            "trailing_stop_at": {
                behind: [
                    {"indicator": far, "period": 10},
                    {"multiply": [atr, {"value": 3}]},
                ]
            },
            "exit_after_bars": 30,
        }
    )


@pytest.mark.parametrize("direction", list(Direction))
@pytest.mark.parametrize("finer", [False, True], ids=["bars", "finer bars"])
def test_no_order_or_exit_looks_ahead(direction, finer):
    bars = random_bars(200)
    other = random_bars(200, seed=8)
    definition = every_order(direction)

    def backtest(bars):
        detail = Detail(finer_bars(bars), pd.Timedelta(minutes=1)) if finer else None
        return run(bars, definition, COSTS, detail)

    result = backtest(bars)
    reasons = {trade.exit_reason for trade in result.trades}
    assert len(result.trades) > 10
    assert len(reasons) >= 3, reasons

    for t in range(len(bars)):
        # Replace every bar after t (and the finer bars inside them) with another random walk.
        changed = backtest(pd.concat([bars.iloc[: t + 1], other.iloc[t + 1 :]]))

        assert changed.equity.iloc[: t + 1].equals(result.equity.iloc[: t + 1])
        finished = [trade for trade in result.trades if trade.exit_time <= bars.index[t]]
        assert changed.trades[: len(finished)] == finished


@pytest.mark.parametrize("direction", list(Direction))
def test_the_engine_never_looks_ahead(direction):
    bars = random_bars(200)
    other = random_bars(200, seed=8)
    definition = rsi_strategy(direction)
    result = run(bars, definition, COSTS)
    assert len(result.trades) > 10

    for t in range(len(bars)):
        # Replace every bar after t with bars from another random walk.
        changed = pd.concat([bars.iloc[: t + 1], other.iloc[t + 1 :]])
        changed_result = run(changed, definition, COSTS)

        assert changed_result.equity.iloc[: t + 1].equals(result.equity.iloc[: t + 1])
        finished = [trade for trade in result.trades if trade.exit_time <= bars.index[t]]
        assert changed_result.trades[: len(finished)] == finished


def test_a_market_order_whose_next_bar_may_not_fill_is_dropped():
    bars = bars_from([(100, 101, 99, 100)] * 5)
    orders = Orders(
        Direction.LONG,
        entries=at(5, 1, 3),
        exits=at(5, 4),
        can_fill=np.array([True, True, False, True, True]),
    )

    result = simulate_orders(bars, orders, BacktestConfig(10_000))

    # Bar 1's signal would fill on bar 2, which may not; bar 3's fills on bar 4.
    [trade] = result.trades
    assert trade.entry_time == bars.index[4]


def test_a_limit_order_does_not_fill_on_a_bar_that_may_not():
    # fmt: off
    bars = bars_from([
        (100, 101,  99, 100),  # 0 signal: buy at 98 or better, for 3 bars
        (100, 101,  99, 100),  # 1
        (100, 101,  97, 100),  # 2 reaches 98, but may not fill
        (100, 101,  97, 100),  # 3 fills at 98
    ])
    # fmt: on
    orders = Orders(
        Direction.LONG,
        entries=at(4, 0),
        entry=Entry("limit", np.full(4, 98.0), expires_after=3),
        can_fill=np.array([True, True, False, True]),
    )

    [trade] = simulate_orders(bars, orders, BacktestConfig(10_000)).trades

    assert (trade.entry_time, trade.entry_price) == (bars.index[3], 98)


def test_with_a_session_entries_fill_only_in_it():
    # Half-hour bars from 08:30 to 17:00 New York time, with an entry signal on every one.
    times = pd.date_range(
        "2026-03-06 08:30", "2026-03-06 17:00", freq="30min", tz="America/New_York"
    )
    bars = bars_from([(100, 101, 99, 100)] * len(times))
    bars.index = times.tz_convert("UTC")
    definition = StrategyDefinition.model_validate(
        {
            "direction": "long",
            "session": {"timezone": "America/New_York", "start": "09:30", "end": "16:00"},
            "entry": {"left": {"price": "close"}, "op": ">", "right": {"value": 0}},
            "exit_after_bars": 1,
        }
    )

    result = run(bars, definition, BacktestConfig(10_000))

    entered = [trade.entry_time.tz_convert("America/New_York") for trade in result.trades]
    assert [f"{time:%H:%M}" for time in entered] == [
        "09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30",
    ]  # fmt: skip


NEW_YORK = {"timezone": "America/New_York", "start": "09:30", "end": "16:00"}
ALWAYS = {"left": {"price": "close"}, "op": ">", "right": {"value": 0}}


def new_york_bars(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    """Bars from (New York time, open, high, low, close) rows."""
    bars = pd.DataFrame(
        [row[1:] for row in rows], columns=["open", "high", "low", "close"], dtype=float
    )
    bars["volume"] = 1.0
    times = pd.DatetimeIndex([row[0] for row in rows]).tz_localize("America/New_York")
    bars.index = times.tz_convert("UTC")
    return bars


def run_flat(bars, *, flat_at="15:55", entries=None, **fields) -> list[SimulatedTrade]:
    """A long with a New York session and a flat-by time, entering wherever `entries` holds
    (on every bar when None), with no slippage or fees."""
    definition = StrategyDefinition.model_validate(
        {
            "direction": "long",
            "session": NEW_YORK,
            "entry": entries or ALWAYS,
            "flat_at": flat_at,
        }
        | fields
    )
    return run(bars, definition, BacktestConfig(10_000)).trades


# fmt: off
CLOSING_MINUTES = new_york_bars([
    # New York time,     open, high,  low, close
    ("2026-03-06 15:40", 100,  101,   99,  100),  # 0 signal
    ("2026-03-06 15:45", 100,  102,  100,  101),  # 1 buy at 100
    ("2026-03-06 15:50", 101,  103,  101,  102),  # 2
    ("2026-03-06 15:55", 103,  104,  102,  103),  # 3 out at the open: 103
    ("2026-03-09 09:30", 104,  105,  103,  104),  # 4 Monday
])
# fmt: on


def test_a_position_leaves_at_the_open_of_the_first_bar_at_the_flat_time():
    first, *_ = run_flat(CLOSING_MINUTES, entries={"time": ["15:40", "15:45"]})

    assert (first.entry_time, first.entry_price) == (CLOSING_MINUTES.index[1], 100)
    assert (first.exit_time, first.exit_price) == (CLOSING_MINUTES.index[3], 103)
    assert first.exit_reason == ExitReason.END_OF_DAY


def test_no_entry_fills_from_the_flat_time():
    # The 15:50 bar's signal would fill at 15:55, the flat time, so it is dropped; the 15:55
    # bar's fills at Monday's open.
    trades = run_flat(CLOSING_MINUTES, entries={"time": ["15:50", "16:00"]})

    assert [trade.entry_time for trade in trades] == [CLOSING_MINUTES.index[4]]


def test_an_entry_order_does_not_fill_from_the_flat_time():
    # Placed on the 15:45 bar to buy on a rise to 103.5, for 2 bars: only the 15:55 bar, at the
    # flat time, reaches it.
    trades = run_flat(
        CLOSING_MINUTES,
        entries={"time": ["15:45", "15:50"]},
        entry_order={"type": "stop", "price": {"value": 103.5}, "expires_after": 2},
    )

    assert trades == []


# fmt: off
SHORT_DAY = new_york_bars([
    ("2026-11-27 12:50", 100, 101,  99, 100),  # 0 signal; the market closes at 13:00
    ("2026-11-27 12:55", 100, 102, 100, 101),  # 1 buy at 100, out at the close: 101
    ("2026-11-30 09:30", 104, 105, 103, 104),  # 2 Monday
])
# fmt: on


def test_a_day_ending_before_the_flat_time_closes_the_position_at_its_last_close():
    [trade] = run_flat(SHORT_DAY, entries={"time": ["12:50", "12:55"]})

    assert (trade.exit_time, trade.exit_price) == (SHORT_DAY.index[1], 101)
    assert trade.exit_reason == ExitReason.END_OF_DAY


def test_out_at_the_close_is_flat_at_the_session_end():
    [trade] = run_flat(CLOSING_MINUTES, flat_at="16:00", entries={"time": ["15:40", "15:45"]})

    assert (trade.exit_time, trade.exit_price) == (CLOSING_MINUTES.index[3], 103)
    assert trade.exit_reason == ExitReason.END_OF_DAY


def test_an_exit_signal_on_the_flat_bar_counts_first():
    [trade] = run_flat(
        CLOSING_MINUTES,
        entries={"time": ["15:40", "15:45"]},
        exit={"time": ["15:50", "15:55"]},
    )

    assert (trade.exit_time, trade.exit_reason) == (CLOSING_MINUTES.index[3], ExitReason.SIGNAL)


def test_with_a_flat_time_no_position_is_held_overnight():
    # Five-minute bars over three New York sessions, entering whenever it can and never
    # leaving on its own.
    days = [
        pd.date_range(f"{day} 09:30", f"{day} 15:55", freq="5min", tz="America/New_York")
        for day in ("2026-03-05", "2026-03-06", "2026-03-09")
    ]
    times = days[0].append(days[1]).append(days[2])
    bars = random_bars(len(times))
    bars.index = times.tz_convert("UTC")

    trades = run_flat(bars)

    assert len(trades) == 3
    for trade in trades:
        entered, left = (
            time.tz_convert("America/New_York") for time in (trade.entry_time, trade.exit_time)
        )
        assert entered.date() == left.date()
        assert f"{left:%H:%M}" == "15:55"
