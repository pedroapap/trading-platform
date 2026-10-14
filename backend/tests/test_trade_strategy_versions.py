"""A trade linked to a strategy records which version of it the trade followed."""

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.errors import InvalidOperationError
from app.schemas.strategy import StrategyUpdate
from app.schemas.trade import TradeCorrection, TradeCreate, TradeUpdate
from app.services import strategies, trades
from tests.helpers import (
    ENTRY_TIME,
    MINIMAL_DEFINITION,
    make_closed_trade,
    make_strategy,
    make_trade,
)


@pytest.fixture
def strategy(db_session, user):
    """A strategy at version 2."""
    strategy = make_strategy(db_session, user)
    changed = {"definition": MINIMAL_DEFINITION | {"stop_loss_pct": 3}}
    strategies.update_strategy(
        db_session, user, strategy.id, StrategyUpdate.model_validate(changed)
    )
    return strategy


def create(db_session, user, **fields):
    data = {
        "symbol": "BTCUSD",
        "direction": "long",
        "entry_price": "100",
        "entry_time": ENTRY_TIME.isoformat(),
        "entry_size": "1",
    } | fields
    return trades.create_trade(db_session, user, TradeCreate.model_validate(data))


def update(db_session, user, trade, **fields):
    return trades.update_trade(db_session, user, trade.id, TradeUpdate.model_validate(fields))


def last_event(db_session, user, trade) -> dict:
    return trades.list_events(db_session, user, trade.id)[-1].new_values


def test_a_linked_trade_follows_the_current_version(db_session, user, strategy):
    trade = create(db_session, user, strategy_id=str(strategy.id))

    assert trade.strategy_version == 2
    assert last_event(db_session, user, trade)["strategy_version"] == 2


def test_a_trade_can_follow_an_earlier_version(db_session, user, strategy):
    trade = create(db_session, user, strategy_id=str(strategy.id), strategy_version=1)

    assert trade.strategy_version == 1


def test_the_version_must_exist(db_session, user, strategy):
    with pytest.raises(InvalidOperationError, match="The strategy has no version 3"):
        create(db_session, user, strategy_id=str(strategy.id), strategy_version=3)


def test_a_version_needs_a_strategy(db_session, user):
    with pytest.raises(InvalidOperationError, match="A strategy version needs a strategy"):
        create(db_session, user, strategy_version=1)


def test_linking_another_strategy_follows_its_current_version(db_session, user, strategy):
    trade = create(db_session, user, strategy_id=str(strategy.id))
    other = make_strategy(db_session, user, "Other")  # at version 1

    update(db_session, user, trade, strategy_id=str(other.id))

    assert (trade.strategy_id, trade.strategy_version) == (other.id, 1)
    assert last_event(db_session, user, trade) == {
        "strategy_id": str(other.id),
        "strategy_version": 1,
    }


def test_choosing_another_version_keeps_the_strategy(db_session, user, strategy):
    trade = create(db_session, user, strategy_id=str(strategy.id))

    update(db_session, user, trade, strategy_version=1)

    assert (trade.strategy_id, trade.strategy_version) == (strategy.id, 1)
    assert last_event(db_session, user, trade) == {"strategy_version": 1}


def test_clearing_the_strategy_clears_its_version(db_session, user, strategy):
    trade = create(db_session, user, strategy_id=str(strategy.id))

    update(db_session, user, trade, strategy_id=None)

    assert (trade.strategy_id, trade.strategy_version) == (None, None)


def test_a_version_alone_needs_a_linked_strategy(db_session, user):
    trade = create(db_session, user)

    with pytest.raises(InvalidOperationError, match="A strategy version needs a strategy"):
        update(db_session, user, trade, strategy_version=1)


def test_the_version_cannot_be_cleared_on_its_own():
    with pytest.raises(ValidationError, match="strategy_version cannot be null"):
        TradeUpdate.model_validate({"strategy_version": None})


def test_a_correction_can_change_the_version(db_session, user, strategy):
    trade = make_closed_trade(db_session, user, "10", strategy_id=strategy.id)  # version 1
    correction = TradeCorrection.model_validate({"strategy_version": 2, "reason": "Was v2"})

    trades.correct_trade(db_session, user, trade.id, correction)

    assert trade.strategy_version == 2


def test_the_trade_api_shows_the_version(client, auth_headers, strategy):
    body = {
        "symbol": "BTCUSD",
        "direction": "long",
        "entry_price": "100",
        "entry_time": ENTRY_TIME.isoformat(),
        "entry_size": "1",
        "strategy_id": str(strategy.id),
    }

    response = client.post("/api/trades", json=body, headers=auth_headers)

    assert (response.status_code, response.json()["strategy_version"]) == (201, 2)


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"strategy_version": 1}, "ck_trades_strategy_version_with_strategy"),
        ({"strategy_version": 3}, "fk_trades_strategy_id_strategy_versions"),
    ],
)
def test_the_database_keeps_versions_consistent(db_session, user, strategy, overrides, constraint):
    if "with_strategy" not in constraint:
        overrides = overrides | {"strategy_id": strategy.id}

    with pytest.raises(IntegrityError, match=constraint):
        make_trade(db_session, user, **overrides)
