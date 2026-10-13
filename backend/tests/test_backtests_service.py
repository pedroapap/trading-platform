import uuid
from datetime import timedelta
from decimal import Decimal

import pandas as pd
import pytest
from pydantic import ValidationError

from app.enums import BacktestStatus
from app.errors import InvalidOperationError
from app.market_data.timeframes import Timeframe
from app.schemas.backtest import BacktestCreate
from app.schemas.strategy import StrategyUpdate
from app.services import backtests, strategies, users
from tests.helpers import ENTRY_TIME, MINIMAL_DEFINITION, make_strategy, random_bars, store_bars


@pytest.fixture
def strategy(db_session, user):
    return make_strategy(db_session, user)


@pytest.fixture
def minute_bars(db_session):
    """Two hours of one-minute BTCUSD bars from ENTRY_TIME."""
    store_bars(db_session, random_bars(120))


def request(strategy_id: uuid.UUID, **overrides: object) -> BacktestCreate:
    fields = {"strategy_id": strategy_id, "symbol": "btcusd", "timeframe": "1m"}
    return BacktestCreate.model_validate(fields | overrides)


def test_a_backtest_starts_pending_with_its_parameters(db_session, user, strategy, minute_bars):
    data = request(strategy.id, initial_capital="5000", fee_pct="0.1")

    backtest = backtests.create_backtest(db_session, user, data)

    assert backtest.status == BacktestStatus.PENDING
    assert (backtest.strategy_version, backtest.symbol, backtest.timeframe) == (
        1,
        "BTCUSD",
        Timeframe.M1,
    )
    assert (backtest.start_ts, backtest.end_ts) == (None, None)
    assert (
        backtest.initial_capital,
        backtest.position_size_pct,
        backtest.fee_pct,
        backtest.slippage_pct,
        backtest.periods_per_year,
    ) == (5000, 100, Decimal("0.1"), 0, 365)


def test_the_version_defaults_to_the_current_one(db_session, user, strategy, minute_bars):
    changed = StrategyUpdate.model_validate(
        {"definition": MINIMAL_DEFINITION | {"stop_loss_pct": 3}}
    )
    strategies.update_strategy(db_session, user, strategy.id, changed)

    latest = backtests.create_backtest(db_session, user, request(strategy.id))
    first = backtests.create_backtest(db_session, user, request(strategy.id, strategy_version=1))

    assert (latest.strategy_version, first.strategy_version) == (2, 1)


def test_the_version_must_exist(db_session, user, strategy, minute_bars):
    with pytest.raises(InvalidOperationError, match="The strategy has no version 2"):
        backtests.create_backtest(db_session, user, request(strategy.id, strategy_version=2))


def test_the_strategy_must_be_the_users_own(db_session, user, strategy, minute_bars):
    other = users.create_user(db_session, "other@example.com", "another-long-password")

    with pytest.raises(InvalidOperationError, match="Unknown strategy"):
        backtests.create_backtest(db_session, other, request(strategy.id))
    with pytest.raises(InvalidOperationError, match="Unknown strategy"):
        backtests.create_backtest(db_session, user, request(uuid.uuid4()))


@pytest.mark.parametrize(
    "overrides",
    [{"symbol": "ETHUSD"}, {"start": (ENTRY_TIME + timedelta(days=1)).isoformat()}],
    ids=["other symbol", "outside the range"],
)
def test_there_must_be_bars(db_session, user, strategy, minute_bars, overrides):
    with pytest.raises(InvalidOperationError, match=r"There are no [A-Z]+ bars in this range"):
        backtests.create_backtest(db_session, user, request(strategy.id, **overrides))


def test_bars_can_be_built_from_finer_ones(db_session, user, strategy, minute_bars):
    backtest = backtests.create_backtest(db_session, user, request(strategy.id, timeframe="1h"))

    assert backtest.timeframe == Timeframe.H1


def test_coarser_bars_cannot_be_split(db_session, user, strategy):
    hourly = random_bars(10)
    hourly.index = pd.date_range("2026-01-05", periods=10, freq="h", tz="UTC")
    store_bars(db_session, hourly)

    with pytest.raises(InvalidOperationError, match="BTCUSD has no 1m bars, or finer bars"):
        backtests.create_backtest(db_session, user, request(strategy.id))


@pytest.mark.parametrize(
    "overrides",
    [
        {"start": "2026-01-02T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
        {"start": "2026-01-01T00:00:00"},  # no time zone
        {"initial_capital": 0},
        {"position_size_pct": 0},
        {"position_size_pct": "100.01"},
        {"fee_pct": 11},
        {"slippage_pct": -1},
        {"periods_per_year": 0},
        {"timeframe": "2h"},
        {"leverage": 2},
    ],
)
def test_invalid_requests_are_rejected(overrides):
    with pytest.raises(ValidationError):
        request(uuid.uuid4(), **overrides)
