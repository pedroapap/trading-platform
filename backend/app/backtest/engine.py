"""The backtest simulation: turns per-bar signals into trades and an equity curve.

Execution model (it follows TradingView's strategy tester where they overlap):
- Signals are evaluated on each bar's close and fill at the next bar's open, so a signal on
  the last bar never fills.
- One position at a time: entry signals are ignored while a position is open. After an exit,
  an entry signal from the exit bar's close onward can re-enter.
- Each entry commits `position_size_pct` of the current equity, entry fee included, so
  100% never overdraws.
- `fee_pct` is charged on each fill's notional, and `slippage_pct` moves each fill's price
  against the trade.
- A short sells at entry and buys back at exit, so its loss has no limit; once equity is
  at or below zero, no new position opens.
- A stop-loss is a percentage of the entry fill price, or a price level read on the bar
  whose signal placed the order; a signal whose levels aren't known yet places no order. It
  is checked against each bar's low (long) or high (short) from the entry bar on, so a level
  already passed at the fill exits at that bar's open. Once reached it fills like a market
  order: at the stop, or at the open when the bar gaps past it, with slippage. A signal
  exit pending from the previous close fills at the open, before the stop.
- A take-profit is a limit order at a percentage of the entry fill price, at a price level
  like a stop-loss, or at a multiple of the risk (the distance from the entry fill to the
  stop-loss). It is checked against each bar's high (long) or low (short), and fills at the
  target, or at the better open when the bar gaps past it, without slippage. When a bar
  reaches both the stop-loss and the take-profit, the stop-loss counts: the bar doesn't say
  which came first, so assume the worse.
- A position still open on the last bar is closed at that bar's close.
- The equity curve is marked to market at each bar's close.
"""

from bisect import bisect_left
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.backtest.orders import Level, Orders
from app.backtest.signals import strategy_orders
from app.enums import Direction, ExitReason
from app.strategies.definition import StrategyDefinition


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float
    position_size_pct: float = 100.0
    fee_pct: float = 0.0
    slippage_pct: float = 0.0


@dataclass(frozen=True)
class SimulatedTrade:
    direction: Direction
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    size: float
    entry_fee: float
    exit_fee: float
    # What slippage cost on both fills, in money.
    slippage: float
    pnl: float
    # Return on the entry notional, in percent, as for live trades.
    pnl_pct: float
    exit_reason: ExitReason


@dataclass(frozen=True)
class BacktestResult:
    trades: list[SimulatedTrade]
    equity: pd.Series


def run(
    bars: pd.DataFrame, definition: StrategyDefinition, config: BacktestConfig
) -> BacktestResult:
    """Backtest a strategy definition on `bars`."""
    return simulate_orders(bars, strategy_orders(definition, bars), config)


def simulate(
    bars: pd.DataFrame,
    entries: np.ndarray,
    exits: np.ndarray | None,
    config: BacktestConfig,
    direction: Direction = Direction.LONG,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
) -> BacktestResult:
    """Trades and equity from boolean entry and exit signals aligned with `bars`, with a
    stop-loss and a take-profit given as percentages."""
    stop_loss = None if stop_loss_pct is None else Level(pct=stop_loss_pct)
    take_profit = None if take_profit_pct is None else Level(pct=take_profit_pct)
    return simulate_orders(bars, Orders(direction, entries, exits, stop_loss, take_profit), config)


def simulate_orders(bars: pd.DataFrame, orders: Orders, config: BacktestConfig) -> BacktestResult:
    """Trades and equity from a strategy's orders on `bars`."""
    opens = bars["open"].to_numpy(dtype=float)
    closes = bars["close"].to_numpy(dtype=float)
    fee = config.fee_pct / 100
    slip = config.slippage_pct / 100
    direction = orders.direction
    # +1 when the position gains as the price rises (long), -1 when it loses (short).
    sign = 1 if direction == Direction.LONG else -1
    # Each bar's extremes against and for the position: where a stop-loss and a
    # take-profit are reached.
    lows, highs = bars["low"].to_numpy(dtype=float), bars["high"].to_numpy(dtype=float)
    adverse, favorable = (lows, highs) if sign == 1 else (highs, lows)
    # A signal whose levels aren't known yet (an indicator warming up) places no order.
    entries = orders.entries & _known(orders.stop_loss) & _known(orders.take_profit)
    # The bars where signals fill: the one after each signal (none after the last bar).
    entry_fills = (np.flatnonzero(entries[:-1]) + 1).tolist()
    exits = orders.exits
    exit_fills = (np.flatnonzero(exits[:-1]) + 1).tolist() if exits is not None else []

    cash = config.initial_capital
    equity = np.full(len(bars), np.nan)
    # Each trade's fields, with its entry and exit bars where it has times.
    made: list[tuple] = []
    earliest_entry = 0
    while cash > 0 and (entry := _first_from(entry_fills, earliest_entry)) is not None:
        entry_price = opens[entry] * (1 + sign * slip)
        # The committed share of equity pays for the notional and its entry fee.
        notional = cash * config.position_size_pct / 100 / (1 + fee)
        entry_fee = notional * fee
        size = notional / entry_price
        signal_exit = _first_from(exit_fills, entry + 1)
        # A signal exit fills at its bar's open, before a stop or target is reached on it.
        watched = slice(entry, len(bars) if signal_exit is None else signal_exit)
        # The order was placed by the signal on the bar before the fill.
        stop = _stop_loss(orders.stop_loss, entry_price, entry - 1, sign)
        target = _take_profit(orders.take_profit, entry_price, stop, entry - 1, sign)
        triggers: list[Trigger] = []
        if stop is not None:
            triggers.append((adverse, stop, -sign))
        if target is not None:
            triggers.append((favorable, target, sign))
        reached = _first_reached(watched, *triggers)
        if reached is None:
            if signal_exit is not None:
                exit_, unslipped_exit, reason = signal_exit, opens[signal_exit], ExitReason.SIGNAL
            else:
                exit_, unslipped_exit, reason = len(bars) - 1, closes[-1], ExitReason.END_OF_DATA
            exit_price = unslipped_exit * (1 - sign * slip)
        elif stop is not None and _reaches(adverse[reached], stop, -sign):
            # Checked first: when a bar reaches both, the stop-loss counts.
            exit_, reason = reached, ExitReason.STOP_LOSS
            unslipped_exit = _fill_price(opens[reached], stop, -sign)
            exit_price = unslipped_exit * (1 - sign * slip)
        else:
            exit_, reason = reached, ExitReason.TAKE_PROFIT
            unslipped_exit = exit_price = _fill_price(opens[reached], target, sign)
        held = slice(entry, exit_)
        equity[held] = cash - entry_fee + sign * size * (closes[held] - entry_price)
        exit_fee = size * exit_price * fee
        pnl = sign * size * (exit_price - entry_price) - entry_fee - exit_fee
        cash += pnl
        equity[exit_] = cash
        slippage = sign * size * (entry_price - opens[entry] + unslipped_exit - exit_price)
        pnl_pct = pnl / (size * entry_price) * 100
        made.append(
            (
                entry,
                entry_price,
                exit_,
                exit_price,
                size,
                entry_fee,
                exit_fee,
                slippage,
                pnl,
                pnl_pct,
                reason,
            )
        )
        earliest_entry = exit_ + 1

    curve = pd.Series(equity, index=bars.index).ffill().fillna(config.initial_capital)
    return BacktestResult(_trades(made, bars.index, direction), curve)


def _trades(
    made: list[tuple], times: pd.DatetimeIndex, direction: Direction
) -> list[SimulatedTrade]:
    """The trades made, with the times of their entry and exit bars. (Times looked up one at a
    time cost more than the rest of a trade's simulation.)"""
    if not made:
        return []
    columns = list(zip(*made, strict=True))
    entry_times = times[np.array(columns[0])]
    exit_times = times[np.array(columns[2])]
    return [
        SimulatedTrade(
            direction=direction,
            entry_time=entry_time,
            entry_price=entry_price,
            exit_time=exit_time,
            exit_price=exit_price,
            size=size,
            entry_fee=entry_fee,
            exit_fee=exit_fee,
            slippage=slippage,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason=reason,
        )
        for (
            _,
            entry_price,
            _,
            exit_price,
            size,
            entry_fee,
            exit_fee,
            slippage,
            pnl,
            pnl_pct,
            reason,
        ), entry_time, exit_time in zip(made, entry_times, exit_times, strict=True)
    ]


def _known(level: Level | None) -> np.ndarray | bool:
    """Where a level is known: everywhere, unless it is a price per bar."""
    return True if level is None or level.at is None else ~np.isnan(level.at)


def _stop_loss(level: Level | None, entry_price: float, signal: int, sign: int) -> float | None:
    """The stop-loss price of a trade entered at `entry_price` on the order of `signal`'s bar."""
    if level is None:
        return None
    if level.at is not None:
        return float(level.at[signal])
    return entry_price * (1 - sign * level.pct / 100)


def _take_profit(
    level: Level | None, entry_price: float, stop: float | None, signal: int, sign: int
) -> float | None:
    """The take-profit price of a trade entered at `entry_price`, whose stop-loss is `stop`."""
    if level is None:
        return None
    if level.at is not None:
        return float(level.at[signal])
    if level.r is not None:
        return entry_price + sign * level.r * abs(entry_price - stop)
    return entry_price * (1 + sign * level.pct / 100)


def _first_from(bars: list[int], start: int) -> int | None:
    """The first of the sorted bar numbers that is at least `start`."""
    position = bisect_left(bars, start)
    return bars[position] if position < len(bars) else None


# A level a price can reach: (values per bar, level, side). Side +1 means reaching it from
# below (at or above the level), -1 from above (at or below it).
Trigger = tuple[np.ndarray, float, int]


def _first_reached(bars: slice, *triggers: Trigger) -> int | None:
    """The first of `bars` on which any trigger's level is reached. Scans chunks that double
    in size, so a level reached k bars in costs O(k), however long the data is."""
    if not triggers:
        return None
    start, size = bars.start, 16
    while start < bars.stop:
        end = min(start + size, bars.stop)
        reached = np.zeros(end - start, dtype=bool)
        for values, level, side in triggers:
            reached |= _reaches(values[start:end], level, side)
        if reached[first := int(reached.argmax())]:
            return start + first
        start, size = end, size * 2
    return None


def _fill_price(open_: float, level: float, side: int) -> float:
    """Where an order at `level` fills on a bar that reached it: at the level, or at the open
    when the bar opened already past it."""
    return open_ if _reaches(open_, level, side) else level


def _reaches(values: np.ndarray | float, level: float, side: int) -> np.ndarray | bool:
    """Whether values are at or past `level` on `side` (+1 above, -1 below)."""
    return values >= level if side > 0 else values <= level
