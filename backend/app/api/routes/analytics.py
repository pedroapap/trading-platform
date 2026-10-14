from typing import Annotated

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.schemas.analytics import PerformanceQuery, PerformanceReport
from app.services import analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/performance")
def performance(
    query: Annotated[PerformanceQuery, Query()], db: DbSession, user: CurrentUser
) -> PerformanceReport:
    """P&L and win rate of closed trades, grouped by strategy or symbol."""
    return PerformanceReport(by=query.by, groups=analytics.performance(db, user, query))
