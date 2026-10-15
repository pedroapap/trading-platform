"""The backtest simulation: turns per-bar signals into trades and an equity curve.

Execution model (it follows TradingView's strategy tester where they overlap):
- Signals are evaluated on each bar's close. An entry fills at the next bar's open, or with
  a limit or stop order at a price read on the signal bar, working from the next bar for a
  number of bars; a newer signal replaces it. A limit fills at its price or a better open,
  without slippage; a stop fills at its price or a worse open, with slippage. A signal on
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
- A trailing stop follows the trade: a percentage behind the best price since the entry
  (the bars before each bar only), or a price level read on each close and used from the
  next bar. It only ever tightens; with a fixed stop-loss too, the tighter one counts. It
  is reached and filled like a stop-loss.
- On the bar where a limit or stop entry fills after the open, a stop-loss reached counts,
  filling at its level (or at the entry price if that is already past it), and a
  take-profit doesn't: the bar doesn't say whether it came after the fill.
- A position still open on the last bar is closed at that bar's close.
- The equity curve is marked to market at each bar's close.
"""

from bisect import bisect_left
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.backtest.orders import Entry, Level, Orders
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
    signals = orders.entries & _known(orders.stop_loss) & _known(orders.take_profit)
    signals &= _known(orders.trailing_stop)
    entering = _Entering(orders.entry, signals & _known(orders.entry), opens, adverse, favorable)
    exits = orders.exits
    exit_fills = (np.flatnonzero(exits[:-1]) + 1).tolist() if exits is not None else []

    cash = config.initial_capital
    equity = np.full(len(bars), np.nan)
    # Each trade's fields, with its entry and exit bars where it has times.
    made: list[tuple] = []
    earliest_signal = 0
    while cash > 0 and (fill := entering.next(earliest_signal, sign)) is not None:
        entry, signal, unslipped_entry, inside = fill
        # A limit order gets its price; market and stop orders fill like market orders.
        slipped = orders.entry.kind != "limit"
        entry_price = unslipped_entry * (1 + sign * slip) if slipped else unslipped_entry
        # The committed share of equity pays for the notional and its entry fee.
        notional = cash * config.position_size_pct / 100 / (1 + fee)
        entry_fee = notional * fee
        size = notional / entry_price
        signal_exit = _first_from(exit_fills, entry + 1)
        # A signal exit fills at its bar's open, before a stop or target is reached on it.
        last = len(bars) if signal_exit is None else signal_exit
        fixed = _stop_loss(orders.stop_loss, entry_price, signal, sign)
        target = _take_profit(orders.take_profit, entry_price, fixed, signal, sign)

        trail = orders.trailing_stop
        stops = None
        if fixed is not None or trail is not None:
            stops = _StopLoss(fixed, trail, entry, signal, unslipped_entry, favorable, sign)
        if inside and stops is not None and _reaches(adverse[entry], stops.level(entry), -sign):
            # Filled inside its bar, whose low (long) reaches the stop: the worst case is that
            # it came after the fill.
            reached = entry
        else:
            if inside and stops is not None:
                # A take-profit reached on the bar of an inside fill may have come before it,
                # and so may its high (long), which a trailing stop doesn't count.
                stops = _StopLoss(fixed, trail, entry + 1, signal, unslipped_entry, favorable, sign)
            first = entry + 1 if inside else entry
            reached = _first_exit(first, last, stops, target, adverse, favorable, sign)
        stop, trailing = (None, False) if stops is None or reached is None else stops.at(reached)
        if reached is None:
            if signal_exit is not None:
                exit_, unslipped_exit, reason = signal_exit, opens[signal_exit], ExitReason.SIGNAL
            else:
                exit_, unslipped_exit, reason = len(bars) - 1, closes[-1], ExitReason.END_OF_DATA
            exit_price = unslipped_exit * (1 - sign * slip)
        elif stop is not None and _reaches(adverse[reached], stop, -sign):
            # Checked first: when a bar reaches both, the stop-loss counts. After an inside
            # fill, the rest of the bar starts at the fill price.
            exit_ = reached
            reason = ExitReason.TRAILING_STOP if trailing else ExitReason.STOP_LOSS
            start = unslipped_entry if inside and reached == entry else opens[reached]
            unslipped_exit = _fill_price(start, stop, -sign)
            exit_price = unslipped_exit * (1 - sign * slip)
        else:
            exit_, reason = reached, ExitReason.TAKE_PROFIT
            unslipped_exit = exit_price = _fill_price(opens[reached], target, sign)
        held = slice(entry, exit_)
        equity[held] = cash - entry_fee + sign * size * (closes[held] - entry_price)
        exit_fee = size * exit_price * fee
        pnl = sign * size * (exit_price - entry_price) - entry_fee - exit_fee
        slippage = sign * size * (entry_price - unslipped_entry + unslipped_exit - exit_price)
        cash += pnl
        equity[exit_] = cash
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
        # Signals from the exit bar's close on can enter again.
        earliest_signal = exit_

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


class _StopLoss:
    """A trade's stop-loss on each bar from `first` on: a fixed level, a trailing one, or the
    tighter of the two. Bars are read in consecutive chunks from `first`, as `_scan` reads
    them, and a trailing stop only ever tightens."""

    def __init__(
        self,
        fixed: float | None,
        trail: Level | None,
        first: int,
        signal: int,
        entry_price: float,
        favorable: np.ndarray,
        sign: int,
    ) -> None:
        self._fixed, self._sign = fixed, sign
        self._trails = trail is not None
        if trail is not None and trail.at is not None:
            # At the tightest level read on the closes since the order was placed.
            self._values, self._factor = trail.at, 1.0
            self._best = _tightest(trail.at[signal:first], sign)
        elif trail is not None:
            # Behind the best price since the entry.
            self._values, self._factor = favorable, 1 - sign * trail.pct / 100
            self._best = entry_price
        self._chunk: tuple[int, np.ndarray] = (first, np.empty(0))

    def levels(self, start: int, end: int) -> np.ndarray | float:
        """The stop-loss on bars start..end-1, each call reading on where the last one ended;
        on each bar a trailing stop counts the bars before it only."""
        if not self._trails:
            return self._fixed
        sign = self._sign
        before = np.concatenate([[self._best], self._values[start : end - 1]])
        best = sign * np.fmax.accumulate(sign * before)
        self._best = sign * np.fmax(sign * best[-1], sign * self._values[end - 1])
        trailing = best * self._factor
        self._chunk = (start, trailing)
        if self._fixed is None:
            return trailing
        return sign * np.fmax(sign * trailing, sign * self._fixed)

    def level(self, bar: int) -> float:
        """The stop-loss on `bar`, the next bar to read."""
        levels = self.levels(bar, bar + 1)
        return float(levels if np.isscalar(levels) else levels[0])

    def at(self, bar: int) -> tuple[float | None, bool]:
        """The stop-loss on `bar`, in the last chunk read, and whether the trailing stop is the
        one that sets it."""
        if not self._trails:
            return self._fixed, False
        start, trailing = self._chunk
        level = float(trailing[bar - start])
        if self._fixed is not None and not self._sign * (level - self._fixed) > 0:
            return self._fixed, False
        return level, True


def _first_exit(
    first: int,
    last: int,
    stops: _StopLoss | None,
    target: float | None,
    adverse: np.ndarray,
    favorable: np.ndarray,
    sign: int,
) -> int | None:
    """The first bar in [first, last) where the stop-loss or the take-profit is reached."""

    def reached(start: int, end: int) -> np.ndarray:
        found = np.zeros(end - start, dtype=bool)
        if stops is not None:
            found |= _reaches(adverse[start:end], stops.levels(start, end), -sign)
        if target is not None:
            found |= _reaches(favorable[start:end], target, sign)
        return found

    return _scan(first, last, reached)


def _tightest(levels: np.ndarray, sign: int) -> float:
    """The tightest known level for a stop: a long's highest, a short's lowest."""
    known = levels[~np.isnan(levels)]
    return float(sign * np.max(sign * known)) if known.size else np.nan


class _Entering:
    """Where entry orders fill."""

    def __init__(
        self,
        order: Entry,
        signals: np.ndarray,
        opens: np.ndarray,
        adverse: np.ndarray,
        favorable: np.ndarray,
    ) -> None:
        self._order, self._opens = order, opens
        bars = np.arange(len(signals))
        if order.kind == "market":
            # The bars where market orders fill: the one after each signal.
            self._fills = (np.flatnonzero(signals[:-1]) + 1).tolist()
            return
        # The order working on each bar is the latest signal's, while it hasn't expired: a
        # newer signal replaces an older order.
        latest = np.maximum.accumulate(np.where(signals, bars, -1))
        self._placed = np.concatenate([[-1], latest[:-1]])
        working = (self._placed >= 0) & (bars - self._placed <= order.expires_after)
        self._prices = np.where(working, order.at[np.maximum(self._placed, 0)], np.nan)
        # A limit order is reached as price moves against the position (a long buys lower); a
        # stop order as it moves with it (a long buys higher).
        self._limit = order.kind == "limit"
        self._adverse, self._favorable = adverse, favorable

    def next(self, earliest_signal: int, sign: int) -> tuple[int, int, float, bool] | None:
        """The next fill of an order placed on `earliest_signal`'s bar or later: its bar, the
        bar of the signal that placed it, its price before slippage, and whether it filled
        inside the bar rather than at its open."""
        if self._order.kind == "market":
            bar = _first_from(self._fills, earliest_signal + 1)
            return None if bar is None else (bar, bar - 1, float(self._opens[bar]), False)
        values, side = (self._adverse, -sign) if self._limit else (self._favorable, sign)
        placed, prices = self._placed, self._prices

        def reached(start: int, end: int) -> np.ndarray:
            fresh = placed[start:end] >= earliest_signal
            return fresh & _reaches(values[start:end], prices[start:end], side)

        bar = _scan(earliest_signal + 1, len(prices), reached)
        if bar is None:
            return None
        price, open_ = float(prices[bar]), float(self._opens[bar])
        # Opened already past the order's price: it fills at the open (better for a limit,
        # worse for a stop).
        at_open = _reaches(open_, price, side)
        return bar, int(placed[bar]), open_ if at_open else price, not at_open


def _known(level: Level | Entry | None) -> np.ndarray | bool:
    """Where a level or an order's price is known: everywhere, unless it is a price per bar."""
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


def _scan(start: int, end: int, reached: Callable[[int, int], np.ndarray]) -> int | None:
    """The first bar in [start, end) where `reached(chunk_start, chunk_end)`, a boolean array
    for a chunk of bars, is true. Scans chunks that double in size, so a bar k bars in costs
    O(k), however long the data is."""
    size = 16
    while start < end:
        stop = min(start + size, end)
        found = reached(start, stop)
        if found[first := int(found.argmax())]:
            return start + first
        start, size = stop, size * 2
    return None


def _fill_price(open_: float, level: float, side: int) -> float:
    """Where an order at `level` fills on a bar that reached it: at the level, or at the open
    when the bar opened already past it."""
    return open_ if _reaches(open_, level, side) else level


def _reaches(values: np.ndarray | float, level: float, side: int) -> np.ndarray | bool:
    """Whether values are at or past `level` on `side` (+1 above, -1 below)."""
    return values >= level if side > 0 else values <= level
