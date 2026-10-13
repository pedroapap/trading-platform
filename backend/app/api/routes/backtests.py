import uuid
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Query, status

from app.deps import CurrentUser, DbSession, JobSessions
from app.schemas.backtest import (
    BacktestCreate,
    BacktestFilters,
    BacktestPage,
    BacktestRead,
    BacktestTradePage,
    BacktestTradeQuery,
    BacktestTradeRead,
    EquityPoint,
)
from app.services import backtests

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def create_backtest(
    body: BacktestCreate,
    db: DbSession,
    user: CurrentUser,
    jobs: BackgroundTasks,
    sessions: JobSessions,
) -> BacktestRead:
    """Queue a backtest; poll GET /backtests/{id} until it is completed or failed."""
    backtest = backtests.create_backtest(db, user, body)
    jobs.add_task(backtests.run_backtest_job, sessions, backtest.id)
    return BacktestRead.model_validate(backtest)


@router.get("/{backtest_id}")
def get_backtest(backtest_id: uuid.UUID, db: DbSession, user: CurrentUser) -> BacktestRead:
    return BacktestRead.model_validate(backtests.get_backtest(db, user, backtest_id))


@router.get("")
def list_backtests(
    filters: Annotated[BacktestFilters, Query()], db: DbSession, user: CurrentUser
) -> BacktestPage:
    """Backtests, newest first, without their equity curves."""
    items, total = backtests.list_backtests(db, user, filters)
    return BacktestPage(
        items=[BacktestRead.model_validate(backtest) for backtest in items],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.get("/{backtest_id}/trades")
def list_trades(
    backtest_id: uuid.UUID,
    query: Annotated[BacktestTradeQuery, Query()],
    db: DbSession,
    user: CurrentUser,
) -> BacktestTradePage:
    """The simulated trades, in the order they were made; empty until the run completes."""
    items, total = backtests.list_trades(db, user, backtest_id, query.limit, query.offset)
    return BacktestTradePage(
        items=[BacktestTradeRead.model_validate(trade) for trade in items],
        total=total,
        limit=query.limit,
        offset=query.offset,
    )


@router.get("/{backtest_id}/equity", response_model=list[EquityPoint])
def get_equity_curve(
    backtest_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[dict[str, Any]]:
    """Equity at up to 1,000 bar closes: the first and last, and the lowest and highest of each
    stretch in between, so drawdowns stay visible. Empty until the run completes."""
    return backtests.get_equity_curve(db, user, backtest_id)
