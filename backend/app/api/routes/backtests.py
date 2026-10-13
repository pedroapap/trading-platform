import uuid

from fastapi import APIRouter, BackgroundTasks, status

from app.deps import CurrentUser, DbSession, JobSessions
from app.schemas.backtest import BacktestCreate, BacktestRead
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
