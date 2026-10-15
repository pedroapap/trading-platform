"""What a strategy asks of the backtest engine, bar by bar. `signals.strategy_orders` prepares
it from a definition, so the engine needs nothing else from the definition."""

from dataclasses import dataclass

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
class Orders:
    """A strategy's orders on a set of bars: entry and exit signals on each bar's close (no
    exits without an exit rule), and where each trade's stop-loss and take-profit sit."""

    direction: Direction
    entries: np.ndarray
    exits: np.ndarray | None = None
    stop_loss: Level | None = None
    take_profit: Level | None = None
