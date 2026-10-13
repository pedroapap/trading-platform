import uuid

import pytest
from sqlalchemy import select

from app.errors import ConflictError, NotFoundError
from app.models import StrategyVersion
from app.schemas.strategy import StrategyCreate
from app.services import strategies, users
from tests.helpers import MINIMAL_DEFINITION


def new(name: str = "RSI dip", **fields) -> StrategyCreate:
    return StrategyCreate(name=name, definition=MINIMAL_DEFINITION, **fields)


def test_create_stores_version_one(db_session, user):
    strategy = strategies.create_strategy(db_session, user, new(description="Buy fear"))

    assert (strategy.name, strategy.description, strategy.current_version) == (
        "RSI dip",
        "Buy fear",
        1,
    )
    assert strategy.current.version == 1
    assert strategy.current.definition == {
        "direction": "long",
        "entry": {
            "left": {"indicator": "rsi", "period": 14, "source": "close"},
            "op": "<",
            "right": {"value": 30.0},
        },
        "exit": None,
        "stop_loss_pct": 2.0,
        "take_profit_pct": None,
    }
    versions = db_session.scalars(select(StrategyVersion)).all()
    assert [(v.version, v.changed_fields) for v in versions] == [(1, None)]


def test_names_must_be_unique_per_user(db_session, user):
    strategies.create_strategy(db_session, user, new())

    with pytest.raises(ConflictError, match="You already have a strategy named 'RSI dip'"):
        strategies.create_strategy(db_session, user, new(" RSI dip "))


def test_get_returns_own_strategies_only(db_session, user):
    own = strategies.create_strategy(db_session, user, new())
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    foreign = strategies.create_strategy(db_session, other, new())

    assert strategies.get_strategy(db_session, user, own.id) is own
    for missing in (foreign.id, uuid.uuid4()):
        with pytest.raises(NotFoundError, match="Strategy not found"):
            strategies.get_strategy(db_session, user, missing)


def test_list_is_sorted_by_name_and_private(db_session, user):
    strategies.create_strategy(db_session, user, new("Trend follow"))
    strategies.create_strategy(db_session, user, new("Breakout"))
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    strategies.create_strategy(db_session, other, new("Alpha"))

    assert [s.name for s in strategies.list_strategies(db_session, user)] == [
        "Breakout",
        "Trend follow",
    ]
