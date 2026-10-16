"""Backtests: a strategy version run over a symbol's bars."""

import hashlib
import logging
import uuid
from dataclasses import asdict
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session, defer

from app.backtest import engine
from app.backtest.charts import downsample_equity
from app.backtest.engine import BacktestConfig, BacktestResult, Detail, SimulatedTrade
from app.backtest.metrics import Split, buy_and_hold, split_summaries, summarize
from app.db import SessionFactory
from app.enums import BacktestStatus
from app.errors import ConflictError, DomainError, InvalidOperationError, NotFoundError
from app.models import Backtest, BacktestTrade, Strategy, StrategyVersion, User
from app.schemas.backtest import BacktestCreate, BacktestFilters
from app.services import instruments, market_data
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
    _require_buildable_timeframes(db, strategy, version, data)
    market_data.require_bars(db, data.symbol, data.timeframe, data.start, data.end)
    if data.detail_timeframe is not None:
        market_data.require_bars(db, data.symbol, data.detail_timeframe, data.start, data.end)
    if data.out_of_sample_from is not None:
        _require_both_sides(db, data)

    backtest = Backtest(
        user_id=user.id,
        strategy_id=strategy.id,
        strategy_version=version,
        symbol=data.symbol,
        timeframe=data.timeframe,
        detail_timeframe=data.detail_timeframe,
        start_ts=data.start,
        end_ts=data.end,
        out_of_sample_from=data.out_of_sample_from,
        initial_capital=data.initial_capital,
        position_size_pct=data.position_size_pct,
        fee_pct=data.fee_pct,
        slippage_pct=data.slippage_pct,
        periods_per_year=data.periods_per_year,
    )
    instruments.register(db, backtest.symbol)
    db.add(backtest)
    db.commit()
    db.refresh(backtest)
    return backtest


def _require_buildable_timeframes(
    db: Session, strategy: Strategy, version: int, data: BacktestCreate
) -> None:
    """The strategy's higher timeframes must be buildable from the backtest's bars."""
    stored = db.scalar(
        select(StrategyVersion.definition).where(
            StrategyVersion.strategy_id == strategy.id, StrategyVersion.version == version
        )
    )
    timeframes = StrategyDefinition.model_validate(stored).timeframes()
    too_fine = sorted(
        (tf for tf in timeframes if not data.timeframe.divides(tf)), key=lambda tf: tf.seconds
    )
    if too_fine:
        raise InvalidOperationError(
            f"The strategy uses {', '.join(too_fine)} bars, which can't be built from"
            f" {data.timeframe} bars"
        )


def _require_both_sides(db: Session, data: BacktestCreate) -> None:
    """Raise unless there are bars on both sides of the out-of-sample start."""
    try:
        market_data.require_bars(
            db, data.symbol, data.timeframe, data.start, data.out_of_sample_from
        )
        market_data.require_bars(db, data.symbol, data.timeframe, data.out_of_sample_from, data.end)
    except InvalidOperationError:
        raise InvalidOperationError(
            "There must be bars on both sides of out_of_sample_from"
        ) from None


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


INTERRUPTED = "Interrupted: the server restarted before the run finished"


def fail_interrupted_backtests(db: Session) -> int:
    """Backtest jobs live in the server process, so after a restart nothing will finish the
    backtests it left pending or running: mark them failed. Returns how many."""
    result = db.execute(
        update(Backtest)
        .where(Backtest.status.in_([BacktestStatus.PENDING, BacktestStatus.RUNNING]))
        .values(
            status=BacktestStatus.FAILED,
            error_message=INTERRUPTED,
            completed_at=func.clock_timestamp(),
        )
    )
    db.commit()
    return result.rowcount


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
    finer = None
    if backtest.detail_timeframe is not None:
        finer = market_data.load_bars(
            db, backtest.symbol, backtest.detail_timeframe, backtest.start_ts, backtest.end_ts
        )
    detail = None if finer is None else Detail(finer, backtest.timeframe.delta)
    definition = StrategyDefinition.model_validate(version.definition)
    result = engine.run(bars, definition, config, detail)

    if result.trades:
        rows = [_trade_row(backtest.id, n, trade) for n, trade in enumerate(result.trades, 1)]
        db.execute(insert(BacktestTrade), rows)
    benchmark = buy_and_hold(bars, config)
    backtest.metrics = asdict(summarize(result, backtest.periods_per_year, benchmark))
    if backtest.out_of_sample_from is not None:
        split = _split(result, bars, config, backtest)
        backtest.split_metrics = asdict(split)
    equity = downsample_equity(result.equity)
    held = benchmark.equity.reindex(equity.index)
    backtest.equity_curve = [
        {"ts": ts.isoformat(), "equity": float(value), "benchmark": float(benchmark_value)}
        for ts, value, benchmark_value in zip(equity.index, equity, held, strict=True)
    ]
    backtest.bars_count = len(bars)
    backtest.first_bar_ts, backtest.last_bar_ts = bars.index[0], bars.index[-1]
    backtest.data_hash = fingerprint(bars) if finer is None else fingerprint(bars, finer)
    backtest.status = BacktestStatus.COMPLETED
    backtest.completed_at = func.clock_timestamp()
    db.commit()


def _split(
    result: BacktestResult, bars: pd.DataFrame, config: BacktestConfig, backtest: Backtest
) -> Split:
    try:
        return split_summaries(
            result,
            bars,
            config,
            pd.Timestamp(backtest.out_of_sample_from),
            backtest.periods_per_year,
        )
    except ValueError as exc:
        # The bars on one side were removed after the backtest was created.
        raise InvalidOperationError(f"Cannot split the results: {exc}") from None


def _trade_row(backtest_id: uuid.UUID, number: int, trade: SimulatedTrade) -> dict[str, Any]:
    # vars() rather than asdict(), which deep-copies every field of every trade.
    return vars(trade) | {"backtest_id": backtest_id, "number": number}


def fingerprint(*frames: pd.DataFrame) -> str:
    """SHA-256 of the bars' start times and values, one set of bars after another (a run's
    bars, then its finer ones): equal for runs that saw the same data."""
    digest = hashlib.sha256()
    for bars in frames:
        digest.update(bars.index.as_unit("ns").asi8.tobytes())
        values = bars[list(market_data.BAR_FIELDS)].to_numpy(dtype=np.float64)
        digest.update(np.ascontiguousarray(values).tobytes())
    return digest.hexdigest()
