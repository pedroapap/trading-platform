"""What a strategy asks of the backtest engine, bar by bar. `signals.strategy_orders` prepares
it from a definition, so the engine needs nothing else from the definition."""

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from app.enums import Direction


@dataclass(frozen=True)
class Level:
    """Where a trade's stop-loss or take-profit sits, given one way:
    - `pct`: percent away from the entry fill price;
    - `at`: a price per bar, taken from the bar whose signal placed the order (NaN where it
      isn't known yet, and such a signal places no order);
    - `r`: a take-profit `r` times as far from the entry as the stop-loss is."""

    pct: float | None = None
    at: np.ndarray | None = None
    r: float | None = None


@dataclass(frozen=True)
class Entry:
    """How an entry signal enters: `market` at the next bar's open, or with a `limit` or
    `stop` order at the price `at` the signal bar (NaN where it isn't known yet: no order),
    working for `expires_after` bars from the next one."""

    kind: Literal["market", "limit", "stop"] = "market"
    at: np.ndarray | None = None
    expires_after: int = 1


@dataclass(frozen=True)
class Orders:
    """A strategy's orders on a set of bars: entry and exit signals on each bar's close (no
    exits without an exit rule), how entries are made, and where each trade's stop-loss,
    take-profit and trailing stop sit."""

    direction: Direction
    entries: np.ndarray
    exits: np.ndarray | None = None
    stop_loss: Level | None = None
    take_profit: Level | None = None
    entry: Entry = field(default_factory=Entry)
    # A stop that follows the trade: `pct` percent behind the best price since the entry, or
    # at the price `at` each bar's close, used from the next bar. It only ever tightens.
    trailing_stop: Level | None = None
    # Exit at the open this many bars after the entry bar, unless something exits first.
    exit_after_bars: int | None = None
    # The bars an entry may fill on; every bar when None.
    can_fill: np.ndarray | None = None
