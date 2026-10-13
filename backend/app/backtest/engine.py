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
- A stop-loss is a percentage of the entry fill price, checked against each bar's low
  (long) or high (short) from the entry bar on. Once reached it fills like a market
  order: at the stop, or at the open when the bar gaps past it, with slippage. A signal
  exit pending from the previous close fills at the open, before the stop.
- A take-profit is a limit order at a percentage of the entry fill price, checked against
  each bar's high (long) or low (short). It fills at the target, or at the better open
  when the bar gaps past it, without slippage. When a bar reaches both the stop-loss and
  the take-profit, the stop-loss counts: the bar doesn't say which came first, so assume
  the worse.
- A position still open on the last bar is closed at that bar's close.
- The equity curve is marked to market at each bar's close.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.backtest.signals import strategy_signals
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
    entries, exits = strategy_signals(definition, bars)
    return simulate(
        bars,
        entries,
        exits,
        config,
        definition.direction,
        definition.stop_loss_pct,
        definition.take_profit_pct,
    )


def simulate(
    bars: pd.DataFrame,
    entries: np.ndarray,
    exits: np.ndarray | None,
    config: BacktestConfig,
    direction: Direction = Direction.LONG,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
) -> BacktestResult:
    """Trades and equity from boolean entry and exit signals aligned with `bars`."""
    opens = bars["open"].to_numpy(dtype=float)
    closes = bars["close"].to_numpy(dtype=float)
    fee = config.fee_pct / 100
    slip = config.slippage_pct / 100
    # +1 when the position gains as the price rises (long), -1 when it loses (short).
    sign = 1 if direction == Direction.LONG else -1
    # Each bar's extremes against and for the position: where a stop-loss and a
    # take-profit are reached.
    lows, highs = bars["low"].to_numpy(dtype=float), bars["high"].to_numpy(dtype=float)
    adverse, favorable = (lows, highs) if sign == 1 else (highs, lows)
    # The bars where signals fill: the one after each signal (none after the last bar).
    entry_fills = np.flatnonzero(entries[:-1]) + 1
    exit_fills = np.flatnonzero(exits[:-1]) + 1 if exits is not None else np.empty(0, dtype=int)

    cash = config.initial_capital
    equity = np.full(len(bars), np.nan)
    trades: list[SimulatedTrade] = []
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
        triggers: list[Trigger] = []
        stop = target = None
        if stop_loss_pct is not None:
            stop = entry_price * (1 - sign * stop_loss_pct / 100)
            triggers.append((adverse, stop, -sign))
        if take_profit_pct is not None:
            target = entry_price * (1 + sign * take_profit_pct / 100)
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
        trades.append(
            SimulatedTrade(
                direction=direction,
                entry_time=bars.index[entry],
                entry_price=entry_price,
                exit_time=bars.index[exit_],
                exit_price=exit_price,
                size=size,
                entry_fee=entry_fee,
                exit_fee=exit_fee,
                slippage=sign * size * (entry_price - opens[entry] + unslipped_exit - exit_price),
                pnl=pnl,
                pnl_pct=pnl / (size * entry_price) * 100,
                exit_reason=reason,
            )
        )
        earliest_entry = exit_ + 1

    curve = pd.Series(equity, index=bars.index).ffill().fillna(config.initial_capital)
    return BacktestResult(trades, curve)


def _first_from(bars: np.ndarray, start: int) -> int | None:
    """The first of the sorted bar numbers that is at least `start`."""
    position = np.searchsorted(bars, start)
    return int(bars[position]) if position < len(bars) else None


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
        if (hits := np.flatnonzero(reached)).size:
            return start + int(hits[0])
        start, size = end, size * 2
    return None


def _fill_price(open_: float, level: float, side: int) -> float:
    """Where an order at `level` fills on a bar that reached it: at the level, or at the open
    when the bar opened already past it."""
    return open_ if _reaches(open_, level, side) else level


def _reaches(values: np.ndarray | float, level: float, side: int) -> np.ndarray | bool:
    """Whether values are at or past `level` on `side` (+1 above, -1 below)."""
    return side * (values - level) >= 0
