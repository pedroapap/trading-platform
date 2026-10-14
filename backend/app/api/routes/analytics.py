import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.schemas.analytics import (
    BacktestComparison,
    EquityQuery,
    PerformanceQuery,
    PerformanceReport,
    RealizedEquity,
)
from app.services import analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/performance")
def performance(
    query: Annotated[PerformanceQuery, Query()], db: DbSession, user: CurrentUser
) -> PerformanceReport:
    """P&L and win rate of closed trades, grouped by strategy, symbol, or the emotions and tags
    recorded in the journal entries about them."""
    return PerformanceReport(by=query.by, groups=analytics.performance(db, user, query))


@router.get("/equity")
def realized_equity(
    query: Annotated[EquityQuery, Query()], db: DbSession, user: CurrentUser
) -> RealizedEquity:
    """Realized P&L over time from closed trades, optionally for one symbol or strategy, with
    its deepest drawdown in money."""
    return analytics.realized_equity(db, user, query)


@router.get("/backtests/{backtest_id}/comparison")
def compare_with_backtest(
    backtest_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> BacktestComparison:
    """A completed backtest next to the live trades that followed the same strategy version on
    the same symbol, entered while its bars ran: trade count, win rate, average return on
    notional and total P&L for each."""
    return analytics.compare_with_backtest(db, user, backtest_id)
