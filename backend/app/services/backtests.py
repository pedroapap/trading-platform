"""Backtests: a strategy version run over a symbol's bars."""

import hashlib
import logging
import uuid
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import func, insert, select
from sqlalchemy.orm import Session, defer

from app.backtest import engine
from app.backtest.charts import downsample_equity
from app.backtest.engine import BacktestConfig, SimulatedTrade
from app.backtest.metrics import summarize
from app.db import SessionFactory
from app.enums import BacktestStatus
from app.errors import ConflictError, DomainError, InvalidOperationError, NotFoundError
from app.models import Backtest, BacktestTrade, Strategy, StrategyVersion, User
from app.schemas.backtest import BacktestCreate, BacktestFilters
from app.services import market_data
from app.strategies.definition import StrategyDefinition

logger = logging.getLogger(__name__)


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


def _own_backtests(user: User):
    # The equity curve is only loaded by the endpoint that returns it.
    return select(Backtest).where(Backtest.user_id == user.id).options(defer(Backtest.equity_curve))


def get_backtest(db: Session, user: User, backtest_id: uuid.UUID) -> Backtest:
    backtest = db.scalar(_own_backtests(user).where(Backtest.id == backtest_id))
    if backtest is None:
        raise NotFoundError("Backtest not found")
    return backtest


def list_backtests(db: Session, user: User, filters: BacktestFilters) -> tuple[list[Backtest], int]:
    """Matching backtests, newest first, plus the total count before pagination."""
    query = _own_backtests(user)
    if filters.strategy_id is not None:
        query = query.where(Backtest.strategy_id == filters.strategy_id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    page = query.order_by(Backtest.created_at.desc()).limit(filters.limit).offset(filters.offset)
    return list(db.scalars(page)), total or 0


def list_trades(
    db: Session, user: User, backtest_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[BacktestTrade], int]:
    """The backtest's trades in the order it made them, plus their total count."""
    backtest = get_backtest(db, user, backtest_id)
    query = select(BacktestTrade).where(BacktestTrade.backtest_id == backtest.id)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    page = query.order_by(BacktestTrade.number).limit(limit).offset(offset)
    return list(db.scalars(page)), total or 0


def get_equity_curve(db: Session, user: User, backtest_id: uuid.UUID) -> list[dict[str, Any]]:
    """The downsampled equity curve; empty until the backtest has completed."""
    found = db.execute(
        select(Backtest.equity_curve).where(Backtest.id == backtest_id, Backtest.user_id == user.id)
    ).one_or_none()
    if found is None:
        raise NotFoundError("Backtest not found")
    return found.equity_curve or []


def run_backtest_job(sessions: SessionFactory, backtest_id: uuid.UUID) -> None:
    """Run a backtest as a background job, in a session of its own."""
    with sessions() as db:
        run_backtest(db, backtest_id)


def run_backtest(db: Session, backtest_id: uuid.UUID) -> Backtest:
    """Run a pending backtest and store its trades, metrics and equity curve. If the run
    fails, nothing it produced is kept and the backtest is marked failed with the reason."""
    backtest = _start(db, backtest_id)
    try:
        _execute(db, backtest)
    except Exception as exc:
        db.rollback()
        if not isinstance(exc, DomainError):
            logger.exception("Backtest %s failed", backtest_id)
        backtest.status = BacktestStatus.FAILED
        backtest.error_message = _failure_reason(exc)
        backtest.completed_at = func.clock_timestamp()
        db.commit()
    return backtest


def _failure_reason(exc: Exception) -> str:
    if isinstance(exc, DomainError):
        return str(exc)
    return f"Unexpected error ({type(exc).__name__}): {exc}"[:2000]


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
