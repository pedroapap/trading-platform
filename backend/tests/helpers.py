"""Constants and helpers shared by tests (import from here, not from conftest)."""

import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.enums import Direction, TradeStatus
from app.models import Backtest, JournalEntry, Strategy, StrategyVersion, Trade, User
from app.services import instruments
from app.services.market_data import import_bars

USER_EMAIL = "trader@example.com"
USER_PASSWORD = "a-long-enough-password"

ENTRY_TIME = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)

# Smallest valid strategy definition: buy when RSI(14) < 30, 2% stop-loss.
MINIMAL_DEFINITION = {
    "direction": "long",
    "entry": {"left": {"indicator": "rsi"}, "op": "<", "right": {"value": 30}},
    "stop_loss_pct": 2.0,
}


# Trades RSI(5) swings with a stop-loss and a take-profit: a few hundred random bars give it
# every kind of exit.
RSI_SWINGS = {
    "direction": "long",
    "entry": {"left": {"indicator": "rsi", "period": 5}, "op": "<", "right": {"value": 35}},
    "exit": {"left": {"indicator": "rsi", "period": 5}, "op": ">", "right": {"value": 60}},
    "stop_loss_pct": 3,
    "take_profit_pct": 4,
}


def make_trade(db: Session, user: User, **overrides: object) -> Trade:
    """Insert an open BTCUSD long (1 @ 100) directly, bypassing services, after registering
    its symbol. A trade given a strategy follows its version 1 unless told otherwise."""
    values: dict[str, object] = {
        "symbol": "BTCUSD",
        "direction": Direction.LONG,
        "entry_price": Decimal("100"),
        "entry_time": ENTRY_TIME,
        "entry_size": Decimal("1"),
    }
    if overrides.get("strategy_id") is not None:
        values["strategy_version"] = 1
    values |= overrides
    instruments.register(db, values["symbol"])
    trade = Trade(user_id=user.id, **values)
    db.add(trade)
    db.flush()
    db.refresh(trade)
    return trade


def make_closed_trade(db: Session, user: User, pnl: str, **overrides: object) -> Trade:
    """Insert a closed BTCUSD long with the given P&L: 1 bought at 100, sold at 100 + pnl an
    hour after ENTRY_TIME."""
    values: dict[str, object] = {
        "status": TradeStatus.CLOSED,
        "exit_price": Decimal(100) + Decimal(pnl),
        "exit_time": ENTRY_TIME + timedelta(hours=1),
        "exit_size": Decimal("1"),
        "pnl": Decimal(pnl),
        "pnl_pct": Decimal(pnl),
    }
    return make_trade(db, user, **(values | overrides))


def make_strategy(
    db: Session,
    user: User,
    name: str = "RSI dip",
    definition: dict[str, object] = MINIMAL_DEFINITION,
) -> Strategy:
    """Insert a strategy with version 1 directly, bypassing services."""
    strategy = Strategy(user_id=user.id, name=name)
    db.add(strategy)
    db.flush()
    db.add(StrategyVersion(strategy_id=strategy.id, version=1, definition=definition))
    db.flush()
    db.refresh(strategy)
    return strategy


def make_backtest(db: Session, user: User, strategy: Strategy, **overrides: object) -> Backtest:
    """Insert a pending daily BTCUSD backtest of the strategy's version 1 directly, bypassing
    services, after registering its symbol."""
    values: dict[str, object] = {
        "strategy_version": 1,
        "symbol": "BTCUSD",
        "timeframe": "1d",
        "initial_capital": Decimal("10000"),
        "position_size_pct": Decimal("100"),
        "fee_pct": Decimal("0"),
        "slippage_pct": Decimal("0"),
        "periods_per_year": 365,
    }
    values |= overrides
    instruments.register(db, values["symbol"])
    backtest = Backtest(user_id=user.id, strategy_id=strategy.id, **values)
    db.add(backtest)
    db.flush()
    db.refresh(backtest)
    return backtest


def make_journal_entry(db: Session, user: User, **overrides: object) -> JournalEntry:
    """Insert a draft note directly, bypassing services."""
    values: dict[str, object] = {"entry_type": "note", "title": "Watching BTC"}
    entry = JournalEntry(user_id=user.id, **(values | overrides))
    db.add(entry)
    db.flush()
    db.refresh(entry)
    return entry


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


def store_bars(db: Session, bars: pd.DataFrame, symbol: str = "BTCUSD") -> None:
    """Store bars, such as random_bars makes, through the CSV importer."""
    import_bars(db, io.StringIO(bars.rename_axis("timestamp").to_csv()), symbol)


def wait_for_backtest(client, headers: dict[str, str], backtest_id: str) -> dict:
    """Poll the API until the backtest has finished. (The test client runs background jobs
    before it returns, so the first poll normally sees the result.)"""
    for _ in range(20):
        backtest = client.get(f"/api/backtests/{backtest_id}", headers=headers).json()
        if backtest["status"] in ("completed", "failed"):
            return backtest
    raise AssertionError(f"backtest {backtest_id} did not finish")
