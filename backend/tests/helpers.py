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


# Your double-bottom strategy, and the editor's first example. The 50-bar SMA crossed below 100
# within the last 48 bars, and price made two swing lows (3 bars on each side) within 0.5% of
# each other within 48 bars: buy with a limit 0.3% above the latest low, for 6 bars, with the
# stop 1% under that low and the target at twice the risk.
# On double_bottom_bars() it makes exactly one trade.
DOUBLE_BOTTOM = {
    "direction": "long",
    "entry": {
        "all": [
            {
                "happened": {
                    "left": {"indicator": "sma", "period": 50},
                    "op": "crosses_below",
                    "right": {"value": 100},
                },
                "within": 48,
            },
            {
                "pattern": "equal_lows",
                "strength": 3,
                "times": 2,
                "within": 48,
                "tolerance_pct": 0.5,
            },
        ]
    },
    "entry_order": {
        "type": "limit",
        "price": {"multiply": [{"indicator": "swing_low", "strength": 3}, {"value": 1.003}]},
        "expires_after": 6,
    },
    "stop_loss_at": {"multiply": [{"indicator": "swing_low", "strength": 3}, {"value": 0.99}]},
    "take_profit_r": 2,
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


# fmt: off
PLANTED = [
    # open,  high,  low, close
    (90.0, 90.3, 89.0, 89.2),  # 80  the slide
    (89.2, 89.4, 88.6, 88.8),  # 81
    (88.8, 89.0, 88.4, 88.5),  # 82
    (88.5, 88.7, 88.2, 88.3),  # 83
    (88.3, 88.5, 88.1, 88.2),  # 84
    (88.2, 88.6, 88.0, 88.5),  # 85  first low: 88.0, a swing low once bar 88 closes
    (88.5, 89.5, 88.4, 89.3),  # 86
    (89.3, 90.5, 89.2, 90.3),  # 87
    (90.3, 91.0, 90.0, 90.8),  # 88  the bounce
    (90.8, 90.9, 90.0, 90.1),  # 89
    (90.1, 90.2, 89.4, 89.5),  # 90
    (89.5, 89.6, 88.9, 89.0),  # 91
    (89.0, 89.1, 88.6, 88.7),  # 92
    (88.7, 88.8, 88.4, 88.5),  # 93
    (88.5, 88.6, 88.3, 88.4),  # 94
    (88.4, 88.7, 88.2, 88.6),  # 95  second low: 88.2, 0.2 above the first (0.5% is 0.441)
    (88.6, 89.4, 88.5, 89.2),  # 96
    (89.2, 89.9, 89.1, 89.7),  # 97
    (89.7, 90.0, 89.4, 89.5),  # 98  the low of 88.2 is confirmed: buy at 88.4646 or better
    (89.5, 89.6, 88.4, 89.0),  # 99  the low of 88.4 reaches it; the stop at 87.318 isn't
    (89.0, 89.5, 88.8, 89.3),  # 100
    (89.3, 90.0, 89.2, 89.9),  # 101
    (89.9, 90.9, 89.8, 90.5),  # 102 the target at 90.7578 is reached
    (90.5, 90.8, 90.3, 90.6),  # 103
    (90.6, 90.9, 90.4, 90.7),  # 104
]
# fmt: on


def double_bottom_bars() -> pd.DataFrame:
    """Hourly bars: 50 at 110, then 30 at 90, so the SMA(50) is exactly 100 on bar 74 and 99.6
    on bar 75, where it crosses below 100; then the planted double bottom."""
    rows = (
        [(110.0, 110.3, 109.7, 110.0)] * 50
        + [(110.0, 110.3, 89.7, 90.0)]  # 50: the drop
        + [(90.0, 90.3, 89.7, 90.0)] * 29  # 51-79: flat, so no swing lows
        + PLANTED
    )
    bars = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    bars["volume"] = 1.0
    bars.index = pd.date_range(ENTRY_TIME.replace(hour=0, minute=0), periods=len(rows), freq="h")
    return bars


def finer_bars(bars: pd.DataFrame, seed: int = 3) -> pd.DataFrame:
    """Three finer bars inside each of `bars` (one width apart), consistent with it: price
    goes from its open to its high and its low, in a random order, then to its close."""
    rng = np.random.default_rng(seed)
    high_first = rng.random(len(bars)) < 0.5
    first = np.where(high_first, bars["high"], bars["low"])
    second = np.where(high_first, bars["low"], bars["high"])
    path = np.stack([bars["open"], first, second, bars["close"]], axis=1)
    starts, ends = path[:, :-1].ravel(), path[:, 1:].ravel()
    offsets = pd.to_timedelta(np.arange(3) * (bars.index[1] - bars.index[0]) / 3)
    times = bars.index.repeat(3) + pd.TimedeltaIndex(np.tile(offsets, len(bars)))
    return pd.DataFrame(
        {
            "open": starts,
            "high": np.maximum(starts, ends),
            "low": np.minimum(starts, ends),
            "close": ends,
            "volume": 1.0,
        },
        index=times,
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
