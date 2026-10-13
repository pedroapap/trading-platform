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
- The equity curve is marked to market at each bar's close.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.enums import ExitReason


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float
    position_size_pct: float = 100.0
    fee_pct: float = 0.0
    slippage_pct: float = 0.0


@dataclass(frozen=True)
class SimulatedTrade:
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


def simulate(
    bars: pd.DataFrame,
    entries: np.ndarray,
    exits: np.ndarray | None,
    config: BacktestConfig,
) -> BacktestResult:
    """Trades and equity from boolean entry and exit signals aligned with `bars`."""
    opens = bars["open"].to_numpy(dtype=float)
    closes = bars["close"].to_numpy(dtype=float)
    fee = config.fee_pct / 100
    slip = config.slippage_pct / 100
    # The bars where signals fill: the one after each signal (none after the last bar).
    entry_fills = np.flatnonzero(entries[:-1]) + 1
    exit_fills = np.flatnonzero(exits[:-1]) + 1 if exits is not None else np.empty(0, dtype=int)

    cash = config.initial_capital
    equity = np.full(len(bars), np.nan)
    trades: list[SimulatedTrade] = []
    earliest_entry = 0
    while (entry := _first_from(entry_fills, earliest_entry)) is not None:
        entry_price = opens[entry] * (1 + slip)
        # The committed share of equity pays for the notional and its entry fee.
        notional = cash * config.position_size_pct / 100 / (1 + fee)
        entry_fee = notional * fee
        size = notional / entry_price
        exit_ = _first_from(exit_fills, entry + 1)
        held = slice(entry, len(bars) if exit_ is None else exit_)
        equity[held] = cash - entry_fee + size * (closes[held] - entry_price)
        if exit_ is None:
            break  # still open at the end: marked to market, but not a trade
        exit_price = opens[exit_] * (1 - slip)
        exit_fee = size * exit_price * fee
        pnl = size * (exit_price - entry_price) - entry_fee - exit_fee
        cash += pnl
        equity[exit_] = cash
        trades.append(
            SimulatedTrade(
                entry_time=bars.index[entry],
                entry_price=entry_price,
                exit_time=bars.index[exit_],
                exit_price=exit_price,
                size=size,
                entry_fee=entry_fee,
                exit_fee=exit_fee,
                slippage=size * (entry_price - opens[entry] + opens[exit_] - exit_price),
                pnl=pnl,
                pnl_pct=pnl / (size * entry_price) * 100,
                exit_reason=ExitReason.SIGNAL,
            )
        )
        earliest_entry = exit_ + 1

    curve = pd.Series(equity, index=bars.index).ffill().fillna(config.initial_capital)
    return BacktestResult(trades, curve)


def _first_from(bars: np.ndarray, start: int) -> int | None:
    """The first of the sorted bar numbers that is at least `start`."""
    position = np.searchsorted(bars, start)
    return int(bars[position]) if position < len(bars) else None
