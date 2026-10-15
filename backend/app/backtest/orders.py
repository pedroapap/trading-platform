"""What a strategy asks of the backtest engine, bar by bar. `signals.strategy_orders` prepares
it from a definition, so the engine needs nothing else from the definition."""

from dataclasses import dataclass

import numpy as np

from app.enums import Direction


@dataclass(frozen=True)
class Level:
    """Where a trade's stop-loss or take-profit sits: `pct` percent away from its entry fill
    price."""

    pct: float


@dataclass(frozen=True)
class Orders:
    """A strategy's orders on a set of bars: entry and exit signals on each bar's close (no
    exits without an exit rule), and where each trade's stop-loss and take-profit sit."""

    direction: Direction
    entries: np.ndarray
    exits: np.ndarray | None = None
    stop_loss: Level | None = None
    take_profit: Level | None = None
