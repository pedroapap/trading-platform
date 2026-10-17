"""The backtest simulation: turns per-bar signals into trades and an equity curve.

Execution model (it follows TradingView's strategy tester where they overlap):
- Signals are evaluated on each bar's close. An entry fills at the next bar's open, or with
  a limit or stop order at a price read on the signal bar, working from the next bar for a
  number of bars; a newer signal replaces it. A limit fills at its price or a better open,
  without slippage; a stop fills at its price or a worse open, with slippage. A signal on
  the last bar never fills.
- One position at a time: entry signals are ignored while a position is open. After an exit,
  an entry signal from the exit bar's close onward can re-enter.
- With a trading session, entries fill only on bars in it: a market order whose next bar is
  outside it is dropped, and a limit or stop order doesn't fill outside it.
- Each entry commits `position_size_pct` of the current equity, entry fee included, so
  100% never overdraws; more borrows the rest (leverage, up to 1000%), at no cost.
- `fee_pct` is charged on each fill's notional, and `slippage_pct` moves each fill's price
  against the trade.
- A short sells at entry and buys back at exit. A margin call closes a position where it
  would leave nothing: its loss, both fees and the exit's slippage use up the equity. It fills
  like a stop-loss at that price, so only a gap past it leaves less than nothing, and a tighter
  stop-loss counts first. A long of 100% of equity or less can't be called; a short of all of
  it is called as the price nears double. Once equity is gone, no new position opens.
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
- A time exit leaves at the open a set number of bars after the entry bar, before a stop or
  target on that bar, as a signal exit does; if both fall on one bar, the signal counts.
- With a flat-by time, no entry fills from it to the end of its trading day, and a position
  still open leaves at the open of the day's first bar starting at or after it, like a time
  exit (a signal or time exit on that bar counts first). A day that ends before it (a
  shortened session) closes the position at the close of its last bar.
- With finer bars (a `Detail`), the bars where it matters what came first are replayed
  through them, in order: the bar where a limit or stop entry fills after the open (where
  and at what price it filled, and whether a stop-loss or take-profit came after it), and a
  bar that reaches both the stop-loss and the take-profit. Where the finer bars are missing
  or don't reach what the bar does, the worst case above stands.
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


@dataclass(frozen=True)
class Detail:
    """Finer bars inside a backtest's bars (`open/high/low/close` by time, in order), to settle
    what came first inside a bar; `width` is the width of the bars they divide."""

    bars: pd.DataFrame
    width: pd.Timedelta


def run(
    bars: pd.DataFrame,
    definition: StrategyDefinition,
    config: BacktestConfig,
    detail: Detail | None = None,
) -> BacktestResult:
    """Backtest a strategy definition on `bars`."""
    return simulate_orders(bars, strategy_orders(definition, bars), config, detail)


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


def simulate_orders(
    bars: pd.DataFrame, orders: Orders, config: BacktestConfig, detail: Detail | None = None
) -> BacktestResult:
    """Trades and equity from a strategy's orders on `bars`, with the finer bars of `detail`
    settling what came first inside a bar where it matters."""
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
    entering = _Entering(
        orders.entry, signals & _known(orders.entry), opens, adverse, favorable, orders.can_fill
    )
    exits = orders.exits
    exit_fills = (np.flatnonzero(exits[:-1]) + 1).tolist() if exits is not None else []
    inside_bars = None if detail is None else _Inside(detail, bars.index, sign)

    cash = config.initial_capital
    # Equity this close to zero is gone: a margin call leaves zero, give or take float rounding.
    gone = config.initial_capital * 1e-9
    equity = np.full(len(bars), np.nan)
    # Each trade's fields, with its entry and exit bars where it has times.
    made: list[tuple] = []
    earliest_signal = 0
    while cash > gone and (fill := entering.next(earliest_signal, sign)) is not None:
        entry, signal, unslipped_entry, inside = fill
        # Where an order filled inside its bar, by the finer bars: (finer bar, price, whether
        # at its open). A finer bar that gapped past the order fills it at its open.
        settled_fill = None
        if inside and inside_bars is not None:
            limit = orders.entry.kind == "limit"
            settled_fill = inside_bars.fill(entry, unslipped_entry, limit)
            if settled_fill is not None:
                unslipped_entry = settled_fill[1]
        # A limit order gets its price; market and stop orders fill like market orders.
        slipped = orders.entry.kind != "limit"
        entry_price = unslipped_entry * (1 + sign * slip) if slipped else unslipped_entry
        # The committed share of equity pays for the notional and its entry fee.
        notional = cash * config.position_size_pct / 100 / (1 + fee)
        entry_fee = notional * fee
        size = notional / entry_price
        signal_exit = _first_from(exit_fills, entry + 1)
        timed_exit = None
        if orders.exit_after_bars is not None and entry + orders.exit_after_bars < len(bars):
            timed_exit = entry + orders.exit_after_bars
        # Out by the flat-by time: at the open of the day's first bar at or after it, or else
        # at the close of the day's last bar. Without one, at the close of the last bar.
        flat_exit, close_exit = None, len(bars) - 1
        if orders.flat is not None:
            if orders.flat.at_open[entry] >= 0:
                flat_exit = int(orders.flat.at_open[entry])
            else:
                close_exit = int(orders.flat.day_last[entry])
        # A signal, timed or flat-by exit fills at its bar's open, before a stop or target is
        # reached on it; if several fall on one bar, the signal counts, then the timed exit.
        open_exit = min(
            (bar for bar in (signal_exit, timed_exit, flat_exit) if bar is not None), default=None
        )
        if open_exit is not None and open_exit > close_exit:
            open_exit = None
        last = close_exit + 1 if open_exit is None else open_exit
        fixed = _stop_loss(orders.stop_loss, entry_price, signal, sign)
        # A take-profit at a multiple of the risk measures it from the strategy's own stop.
        target = _take_profit(orders.take_profit, entry_price, fixed, signal, sign)
        called = _margin_call(cash - entry_fee, size, entry_price, sign, fee, slip)
        margin_call = called is not None and (fixed is None or sign * (called - fixed) > 0)
        if margin_call:
            fixed = called

        trail = orders.trailing_stop
        stops = None
        if fixed is not None or trail is not None:
            stops = _StopLoss(fixed, trail, entry, signal, unslipped_entry, favorable, sign)
        # An exit the finer bars settled: (whether the stop-loss, price before slippage).
        settled_exit = None
        if settled_fill is not None:
            # Replay the rest of the fill's bar.
            finer, price, at_open = settled_fill
            stop = None if stops is None else stops.level(entry)
            after = None if at_open else price
            settled_exit = inside_bars.exit(finer, entry, stop, target, after)
        if settled_exit is not None:
            reached = entry
        elif inside and settled_fill is None and _stopped(stops, adverse, entry, sign):
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
        both = (
            settled_exit is None
            and reached is not None
            and stop is not None
            and target is not None
            and _reaches(adverse[reached], stop, -sign)
            and _reaches(favorable[reached], target, sign)
        )
        if both and inside_bars is not None:
            # The bar reaches both the stop-loss and the take-profit: its finer bars say which
            # came first.
            settled_exit = inside_bars.exit(None, reached, stop, target)
        if reached is None:
            if open_exit is not None:
                exit_, unslipped_exit = open_exit, opens[open_exit]
                reason = (
                    ExitReason.SIGNAL
                    if open_exit == signal_exit
                    else ExitReason.TIME_EXIT
                    if open_exit == timed_exit
                    else ExitReason.END_OF_DAY
                )
            else:
                exit_, unslipped_exit = close_exit, closes[close_exit]
                reason = ExitReason.END_OF_DATA if orders.flat is None else ExitReason.END_OF_DAY
            exit_price = unslipped_exit * (1 - sign * slip)
        elif settled_exit is not None:
            exit_ = reached
            stopped, unslipped_exit = settled_exit
            if stopped:
                reason = _stop_reason(trailing, margin_call)
                exit_price = unslipped_exit * (1 - sign * slip)
            else:
                reason, exit_price = ExitReason.TAKE_PROFIT, unslipped_exit
        elif stop is not None and _reaches(adverse[reached], stop, -sign):
            # Checked first: when a bar reaches both, the stop-loss counts. After an inside
            # fill, the rest of the bar starts at the fill price.
            exit_ = reached
            reason = _stop_reason(trailing, margin_call)
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


class _Inside:
    """The finer bars inside each bar of a backtest, replayed in order where it matters what
    came first inside a bar. Where they are missing, or don't reach what the bar does, nothing
    is settled and the worst case stands."""

    def __init__(self, detail: Detail, times: pd.DatetimeIndex, sign: int) -> None:
        index = detail.bars.index
        self._first = index.searchsorted(times)
        self._end = index.searchsorted(times + detail.width)
        self._opens = detail.bars["open"].to_numpy(dtype=float)
        lows = detail.bars["low"].to_numpy(dtype=float)
        highs = detail.bars["high"].to_numpy(dtype=float)
        self._adverse, self._favorable = (lows, highs) if sign == 1 else (highs, lows)
        self._sign = sign

    def fill(self, bar: int, price: float, limit: bool) -> tuple[int, float, bool] | None:
        """Where an order at `price` fills inside `bar`: the finer bar, the price, and whether
        it filled at that finer bar's open."""
        sign = self._sign
        values, side = (self._adverse, -sign) if limit else (self._favorable, sign)
        for finer in range(self._first[bar], self._end[bar]):
            if _reaches(values[finer], price, side):
                at_open = _reaches(self._opens[finer], price, side)
                return finer, float(self._opens[finer]) if at_open else price, at_open
        return None

    def exit(
        self,
        first: int | None,
        bar: int,
        stop: float | None,
        target: float | None,
        after: float | None = None,
    ) -> tuple[bool, float] | None:
        """The first exit inside `bar`, from its finer bar `first` (or its first one) on:
        whether it is the stop-loss (which counts first on each finer bar) and its price before
        slippage. `after` is the price of an order filled inside that first finer bar: there it
        stands for the open, and a take-profit doesn't count."""
        sign = self._sign
        start = self._first[bar] if first is None else first
        for finer in range(start, self._end[bar]):
            filled_inside = after is not None and finer == start
            open_ = after if filled_inside else self._opens[finer]
            if stop is not None and _reaches(self._adverse[finer], stop, -sign):
                return True, float(_fill_price(open_, stop, -sign))
            # After an inside fill, the finer bar's high (long) may have come before it.
            reached = target is not None and _reaches(self._favorable[finer], target, sign)
            if reached and not filled_inside:
                return False, float(_fill_price(open_, target, sign))
        return None


def _stopped(stops: "_StopLoss | None", adverse: np.ndarray, bar: int, sign: int) -> bool:
    """Whether the stop-loss is reached on `bar`, the next bar `stops` reads."""
    return stops is not None and bool(_reaches(adverse[bar], stops.level(bar), -sign))


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
        # The best so far, then each bar's value, as a long's (higher is tighter); the best on
        # each bar is the running maximum of what came before it.
        seen = np.empty(end - start + 1)
        seen[0] = sign * self._best
        np.multiply(self._values[start:end], sign, out=seen[1:])
        np.fmax.accumulate(seen, out=seen)
        self._best = sign * seen[-1]
        trailing = seen[:-1] * (sign * self._factor)
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
    """The tightest known level for a stop: a long's highest, a short's lowest. (A few levels,
    those read between a signal and its fill: quicker in Python than in numpy.)"""
    tightest = np.nan
    for level in levels.tolist():
        if level == level and not sign * (level - tightest) <= 0:  # skip NaN; NaN beats nothing
            tightest = level
    return tightest


class _Entering:
    """Where entry orders fill."""

    def __init__(
        self,
        order: Entry,
        signals: np.ndarray,
        opens: np.ndarray,
        adverse: np.ndarray,
        favorable: np.ndarray,
        can_fill: np.ndarray | None,
    ) -> None:
        self._order, self._opens = order, opens
        bars = np.arange(len(signals))
        if can_fill is None:
            can_fill = np.ones(len(signals), dtype=bool)
        if order.kind == "market":
            # The bars where market orders fill: the one after each signal, if it may.
            self._fills = (np.flatnonzero(signals[:-1] & can_fill[1:]) + 1).tolist()
            return
        # The order working on each bar is the latest signal's, while it hasn't expired: a
        # newer signal replaces an older order.
        latest = np.maximum.accumulate(np.where(signals, bars, -1))
        self._placed = np.concatenate([[-1], latest[:-1]])
        working = (self._placed >= 0) & (bars - self._placed <= order.expires_after) & can_fill
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


def _margin_call(
    equity: float, size: float, entry_price: float, sign: int, fee: float, slip: float
) -> float | None:
    """Where a position of `size` entered at `entry_price` loses all of `equity`, the exit's
    slippage and fee included; None for a long that can't lose that much, its price having to
    fall to zero first."""
    # The exit fill where the loss plus the exit fee is the equity, and the level whose fill,
    # after slippage against the position, it is.
    fill = (sign * size * entry_price - equity) / (size * (sign - fee))
    called = fill / (1 - sign * slip)
    return None if called <= entry_price * 1e-9 else called


def _stop_reason(trailing: bool, margin_call: bool) -> ExitReason:
    """Why a stop closed a trade: the trailing stop, the margin call or the stop-loss, whichever
    was the tightest."""
    if trailing:
        return ExitReason.TRAILING_STOP
    return ExitReason.MARGIN_CALL if margin_call else ExitReason.STOP_LOSS


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
