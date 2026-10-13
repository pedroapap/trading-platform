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


def test_an_open_position_is_marked_to_market_until_the_end():
    # Bar 1's signal buys 100 @ 100 on bar 2 with the whole 10,000; nothing sells.
    result = simulate(TWELVE_BARS, at(12, 1), None, BacktestConfig(initial_capital=10_000))

    closes = TWELVE_BARS["close"].tolist()
    assert result.equity.tolist() == [10_000, 10_000] + [100 * close for close in closes[2:]]


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
