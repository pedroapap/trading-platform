"""Constants and helpers shared by tests (import from here, not from conftest)."""

from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.enums import Direction
from app.models import Strategy, StrategyVersion, Trade, User

USER_EMAIL = "trader@example.com"
USER_PASSWORD = "a-long-enough-password"

ENTRY_TIME = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)

# Smallest valid strategy definition: buy when RSI(14) < 30, 2% stop-loss.
MINIMAL_DEFINITION = {
    "direction": "long",
    "entry": {"left": {"indicator": "rsi"}, "op": "<", "right": {"value": 30}},
    "stop_loss_pct": 2.0,
}


def make_trade(db: Session, user: User, **overrides: object) -> Trade:
    """Insert an open BTCUSD long (1 @ 100) directly, bypassing services."""
    values: dict[str, object] = {
        "symbol": "BTCUSD",
        "direction": Direction.LONG,
        "entry_price": Decimal("100"),
        "entry_time": ENTRY_TIME,
        "entry_size": Decimal("1"),
    }
    trade = Trade(user_id=user.id, **(values | overrides))
    db.add(trade)
    db.flush()
    db.refresh(trade)
    return trade


def make_strategy(db: Session, user: User, name: str = "RSI dip") -> Strategy:
    """Insert a strategy with version 1 directly, bypassing services."""
    strategy = Strategy(user_id=user.id, name=name)
    db.add(strategy)
    db.flush()
    db.add(StrategyVersion(strategy_id=strategy.id, version=1, definition=MINIMAL_DEFINITION))
    db.flush()
    db.refresh(strategy)
    return strategy


def random_bars(length: int = 300, seed: int = 7) -> pd.DataFrame:
    """Consistent 1-minute OHLCV bars following a random walk around 100."""
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, length))
    open_ = np.concatenate([[100.0], close[:-1]]) + rng.normal(0, 0.2, length)
    return pd.DataFrame(
        {
            "open": open_,
            "high": np.maximum(open_, close) + rng.uniform(0, 0.5, length),
            "low": np.minimum(open_, close) - rng.uniform(0, 0.5, length),
            "close": close,
            "volume": rng.uniform(1, 10, length),
        },
        index=pd.date_range(ENTRY_TIME, periods=length, freq="min"),
    )
