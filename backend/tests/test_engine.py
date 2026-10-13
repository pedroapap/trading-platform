"""Golden tests: small bar tables whose trades and equity are worked out by hand."""

from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.backtest.engine import BacktestConfig, SimulatedTrade, simulate
from app.enums import Direction, ExitReason
from app.services.pnl import trade_pnl
from tests.helpers import ENTRY_TIME, random_bars


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
