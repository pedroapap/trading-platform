from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.enums import BacktestStatus, Direction, ExitReason
from app.models import BacktestTrade
from app.schemas.strategy import StrategyUpdate
from app.security import create_access_token
from app.services import strategies, users
from tests.helpers import (
    MINIMAL_DEFINITION,
    make_backtest,
    make_closed_trade,
    make_strategy,
    make_trade,
)

# The backtest ran over ten hourly bars from T0: live trades entered in [T0, T0 + 10h) count.
T0 = datetime(2026, 1, 5, tzinfo=UTC)
HOUR = timedelta(hours=1)


@pytest.fixture
def strategy(db_session, user):
    """A strategy at version 2."""
    strategy = make_strategy(db_session, user)
    changed = {"definition": MINIMAL_DEFINITION | {"stop_loss_pct": 3}}
    strategies.update_strategy(
        db_session, user, strategy.id, StrategyUpdate.model_validate(changed)
    )
    return strategy


@pytest.fixture
def backtest(db_session, user, strategy):
    """A completed hourly BTCUSD backtest of version 2 with three trades: +5%, -2%, +3%."""
    backtest = make_backtest(
        db_session,
        user,
        strategy,
        strategy_version=2,
        timeframe="1h",
        status=BacktestStatus.COMPLETED,
        metrics={},
        equity_curve=[],
        first_bar_ts=T0,
        last_bar_ts=T0 + 9 * HOUR,
    )
    for number, (pnl, pct) in enumerate([("50", "5"), ("-20", "-2"), ("30", "3")], start=1):
        db_session.add(
            BacktestTrade(
                backtest_id=backtest.id,
                number=number,
                direction=Direction.LONG,
                entry_time=T0 + number * HOUR,
                entry_price=Decimal(100),
                exit_time=T0 + number * HOUR,
                exit_price=Decimal(100),
                size=Decimal(10),
                entry_fee=Decimal(0),
                exit_fee=Decimal(0),
                slippage=Decimal(0),
                pnl=Decimal(pnl),
                pnl_pct=Decimal(pct),
                exit_reason=ExitReason.SIGNAL,
            )
        )
    db_session.flush()
    return backtest


def live_trade(db_session, user, strategy, pnl, entered, **overrides):
    values = {
        "strategy_id": strategy.id,
        "strategy_version": 2,
        "entry_time": entered,
        "exit_time": entered + timedelta(minutes=30),
    }
    return make_closed_trade(db_session, user, pnl, **(values | overrides))


def compare(client, auth_headers, backtest_id):
    return client.get(f"/api/analytics/backtests/{backtest_id}/comparison", headers=auth_headers)


def test_live_trades_are_compared_with_the_backtest(
    client, auth_headers, db_session, user, strategy, backtest
):
    # Counted: same version and symbol, entered within the backtest's bars.
    live_trade(db_session, user, strategy, "40", T0 + HOUR, pnl_pct=Decimal(4))
    live_trade(db_session, user, strategy, "-10", T0 + 5 * HOUR, pnl_pct=Decimal(-6), leverage=2)
    # Not counted.
    live_trade(db_session, user, strategy, "99", T0 + 2 * HOUR, strategy_version=1)
    live_trade(db_session, user, strategy, "99", T0 + 2 * HOUR, symbol="ETHUSD")
    live_trade(db_session, user, strategy, "99", T0 + 10 * HOUR)  # after the last bar
    live_trade(db_session, user, strategy, "99", T0 - HOUR)  # before the first bar
    make_trade(db_session, user, strategy_id=strategy.id, strategy_version=2, entry_time=T0)

    response = compare(client, auth_headers, backtest.id)

    assert response.status_code == 200
    comparison = response.json()
    assert (comparison["strategy_version"], comparison["symbol"]) == (2, "BTCUSD")
    assert (comparison["period_start"], comparison["period_end"]) == (
        "2026-01-05T00:00:00Z",
        "2026-01-05T10:00:00Z",
    )
    # The leveraged trade's -6% on margin is -3% on its notional: (4 - 3) / 2 = 0.5.
    assert comparison["live"] == {
        "num_trades": 2,
        "win_rate_pct": 50,
        "average_return_pct": "0.5",
        "total_pnl": "30",
    }
    assert comparison["backtest"] == {
        "num_trades": 3,
        "win_rate_pct": pytest.approx(200 / 3),
        "average_return_pct": "2",
        "total_pnl": "60",
    }


def test_without_live_trades_there_is_nothing_to_average(client, auth_headers, backtest):
    live = compare(client, auth_headers, backtest.id).json()["live"]

    assert live == {
        "num_trades": 0,
        "win_rate_pct": None,
        "average_return_pct": None,
        "total_pnl": "0",
    }


def test_only_a_completed_backtest_can_be_compared(
    client, auth_headers, db_session, user, strategy
):
    pending = make_backtest(db_session, user, strategy)

    response = compare(client, auth_headers, pending.id)

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "Only a completed backtest can be compared; this one is pending"
    )


def test_another_users_backtest_is_not_found(client, db_session, backtest):
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    headers = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}

    assert compare(client, headers, backtest.id).status_code == 404
