from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.schemas.analytics import (
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
