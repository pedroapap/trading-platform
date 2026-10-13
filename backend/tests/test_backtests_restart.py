from contextlib import nullcontext

from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.enums import BacktestStatus
from app.main import app
from app.services import backtests
from tests.helpers import make_backtest, make_strategy


def backtests_in_every_state(db_session, user):
    strategy = make_strategy(db_session, user)
    return {
        BacktestStatus.PENDING: make_backtest(db_session, user, strategy),
        BacktestStatus.RUNNING: make_backtest(
            db_session, user, strategy, status=BacktestStatus.RUNNING
        ),
        BacktestStatus.COMPLETED: make_backtest(
            db_session, user, strategy, status=BacktestStatus.COMPLETED, metrics={}, equity_curve=[]
        ),
        BacktestStatus.FAILED: make_backtest(
            db_session, user, strategy, status=BacktestStatus.FAILED, error_message="no data"
        ),
    }


def test_unfinished_backtests_are_failed(db_session, user):
    by_status = backtests_in_every_state(db_session, user)

    assert backtests.fail_interrupted_backtests(db_session) == 2

    for backtest in by_status.values():
        db_session.refresh(backtest)
    assert [backtest.status for backtest in by_status.values()] == [
        BacktestStatus.FAILED,
        BacktestStatus.FAILED,
        BacktestStatus.COMPLETED,
        BacktestStatus.FAILED,
    ]
    assert by_status[BacktestStatus.PENDING].error_message == backtests.INTERRUPTED
    assert by_status[BacktestStatus.RUNNING].completed_at is not None
    assert by_status[BacktestStatus.FAILED].error_message == "no data"


def test_the_server_fails_them_when_it_starts(db_session, user):
    pending = make_backtest(db_session, user, make_strategy(db_session, user))
    app.dependency_overrides[get_session_factory] = lambda: lambda: nullcontext(db_session)
    try:
        with TestClient(app):
            pass
    finally:
        app.dependency_overrides.pop(get_session_factory, None)

    db_session.refresh(pending)
    assert (pending.status, pending.error_message) == (BacktestStatus.FAILED, backtests.INTERRUPTED)
