import uuid

import pytest
from sqlalchemy import select

from app.errors import ConflictError, NotFoundError
from app.models import StrategyVersion
from app.schemas.strategy import StrategyCreate, StrategyUpdate
from app.services import strategies, users
from tests.helpers import MINIMAL_DEFINITION, make_strategy


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


def versions(db, strategy) -> list[StrategyVersion]:
    query = select(StrategyVersion).where(StrategyVersion.strategy_id == strategy.id)
    return list(db.scalars(query.order_by(StrategyVersion.version)))


def update(db, user, strategy, **fields):
    return strategies.update_strategy(db, user, strategy.id, StrategyUpdate(**fields))


def test_metadata_changes_do_not_create_versions(db_session, user):
    strategy = strategies.create_strategy(db_session, user, new(description="old"))

    updated = update(db_session, user, strategy, name="RSI dip v2", description=None)

    assert (updated.name, updated.description, updated.current_version) == ("RSI dip v2", None, 1)
    assert len(versions(db_session, strategy)) == 1


def test_a_changed_definition_becomes_the_next_version(db_session, user):
    strategy = strategies.create_strategy(db_session, user, new())
    changed = MINIMAL_DEFINITION | {"stop_loss_pct": 3.0, "take_profit_pct": 9.0}

    updated = update(db_session, user, strategy, definition=changed)

    assert updated.current_version == 2
    assert updated.current.definition["stop_loss_pct"] == 3.0
    first, second = versions(db_session, strategy)
    assert first.definition["stop_loss_pct"] == 2.0  # history is untouched
    assert second.changed_fields == ["stop_loss_pct", "take_profit_pct"]


def test_an_identical_definition_is_not_a_new_version(db_session, user):
    strategy = strategies.create_strategy(db_session, user, new())

    update(db_session, user, strategy, definition=dict(MINIMAL_DEFINITION))

    assert strategy.current_version == 1
    assert len(versions(db_session, strategy)) == 1


def test_defaults_missing_from_a_stored_definition_are_not_changes(db_session, user):
    # Stored as written, without the defaults (RSI's period and source) that the model fills
    # in: as a version saved before the language gained a field looks.
    strategy = make_strategy(db_session, user, definition=MINIMAL_DEFINITION)

    update(db_session, user, strategy, definition=dict(MINIMAL_DEFINITION))

    assert strategy.current_version == 1
    assert len(versions(db_session, strategy)) == 1


def test_renaming_onto_an_existing_name_is_a_conflict(db_session, user):
    strategies.create_strategy(db_session, user, new("Breakout"))
    strategy = strategies.create_strategy(db_session, user, new("RSI dip"))

    with pytest.raises(ConflictError, match="named 'Breakout'"):
        update(db_session, user, strategy, name="Breakout")


def test_updating_a_foreign_strategy_is_not_found(db_session, user):
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    foreign = strategies.create_strategy(db_session, other, new())

    with pytest.raises(NotFoundError):
        update(db_session, user, foreign, name="Mine now")


def test_name_and_definition_cannot_be_cleared():
    for field in ("name", "definition"):
        with pytest.raises(ValueError, match=f"{field} cannot be null"):
            StrategyUpdate.model_validate({field: None})
