"""Backtests: a strategy version run over a symbol's bars."""

import hashlib
import uuid
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session

from app.backtest import engine
from app.backtest.charts import downsample_equity
from app.backtest.engine import BacktestConfig, SimulatedTrade
from app.backtest.metrics import summarize
from app.enums import BacktestStatus
from app.errors import ConflictError, InvalidOperationError, NotFoundError
from app.models import Backtest, BacktestTrade, Strategy, StrategyVersion, User
from app.schemas.backtest import BacktestCreate
from app.services import market_data
from app.strategies.definition import StrategyDefinition


def create_backtest(db: Session, user: User, data: BacktestCreate) -> Backtest:
    """A pending backtest, after checking the strategy version and that there are bars."""
    owned = select(Strategy).where(Strategy.id == data.strategy_id, Strategy.user_id == user.id)
    strategy = db.scalar(owned)
    if strategy is None:
        raise InvalidOperationError("Unknown strategy")
    version = data.strategy_version or strategy.current_version
    if version > strategy.current_version:
        raise InvalidOperationError(f"The strategy has no version {version}")
    market_data.require_bars(db, data.symbol, data.timeframe, data.start, data.end)

    backtest = Backtest(
        user_id=user.id,
        strategy_id=strategy.id,
        strategy_version=version,
        symbol=data.symbol,
        timeframe=data.timeframe,
        start_ts=data.start,
        end_ts=data.end,
        initial_capital=data.initial_capital,
        position_size_pct=data.position_size_pct,
        fee_pct=data.fee_pct,
        slippage_pct=data.slippage_pct,
        periods_per_year=data.periods_per_year,
    )
    db.add(backtest)
    db.commit()
    db.refresh(backtest)
    return backtest


def run_backtest(db: Session, backtest_id: uuid.UUID) -> Backtest:
    """Run a pending backtest and store its trades, metrics and equity curve."""
    backtest = _start(db, backtest_id)
    _execute(db, backtest)
    return backtest


def _start(db: Session, backtest_id: uuid.UUID) -> Backtest:
    """Mark the backtest running, committed, so an interrupted run leaves a trace."""
    backtest = db.scalar(select(Backtest).where(Backtest.id == backtest_id).with_for_update())
    if backtest is None:
        raise NotFoundError("Backtest not found")
    if backtest.status != BacktestStatus.PENDING:
        raise ConflictError(f"Cannot run a {backtest.status} backtest")
    backtest.status = BacktestStatus.RUNNING
    backtest.started_at = func.clock_timestamp()
    db.commit()
    return backtest


def _execute(db: Session, backtest: Backtest) -> None:
    bars = market_data.load_bars(
        db, backtest.symbol, backtest.timeframe, backtest.start_ts, backtest.end_ts
    )
    version = db.scalar(
        select(StrategyVersion).where(
            StrategyVersion.strategy_id == backtest.strategy_id,
            StrategyVersion.version == backtest.strategy_version,
        )
    )
    config = BacktestConfig(
        initial_capital=float(backtest.initial_capital),
        position_size_pct=float(backtest.position_size_pct),
        fee_pct=float(backtest.fee_pct),
        slippage_pct=float(backtest.slippage_pct),
    )
    result = engine.run(bars, StrategyDefinition.model_validate(version.definition), config)

    if result.trades:
        rows = [_trade_row(backtest.id, n, trade) for n, trade in enumerate(result.trades, 1)]
        db.execute(insert(BacktestTrade), rows)
    backtest.metrics = asdict(summarize(result, backtest.periods_per_year))
    backtest.equity_curve = [
        {"ts": ts.isoformat(), "equity": float(equity)}
        for ts, equity in downsample_equity(result.equity).items()
    ]
    backtest.bars_count = len(bars)
    backtest.first_bar_ts, backtest.last_bar_ts = bars.index[0], bars.index[-1]
    backtest.data_hash = fingerprint(bars)
    backtest.status = BacktestStatus.COMPLETED
    backtest.completed_at = func.clock_timestamp()
    db.commit()


def _trade_row(backtest_id: uuid.UUID, number: int, trade: SimulatedTrade) -> dict[str, Any]:
    # vars() rather than asdict(), which deep-copies every field of every trade.
    return vars(trade) | {"backtest_id": backtest_id, "number": number}


def fingerprint(bars: pd.DataFrame) -> str:
    """SHA-256 of the bars' start times and values: equal for runs that saw the same data."""
    digest = hashlib.sha256(bars.index.as_unit("ns").asi8.tobytes())
    values = bars[list(market_data.BAR_FIELDS)].to_numpy(dtype=np.float64)
    digest.update(np.ascontiguousarray(values).tobytes())
    return digest.hexdigest()
