import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import Strategy, StrategyVersion
from app.services import users
from tests.helpers import MINIMAL_DEFINITION, make_strategy, make_trade


def test_a_strategy_starts_at_version_one(db_session, user):
    strategy = make_strategy(db_session, user)

    assert strategy.current_version == 1
    version = db_session.query(StrategyVersion).filter_by(strategy_id=strategy.id).one()
    assert version.definition == MINIMAL_DEFINITION
    assert version.changed_fields is None


def test_names_are_unique_per_user(db_session, user):
    make_strategy(db_session, user, name="Breakout")
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    make_strategy(db_session, other, name="Breakout")  # another user may reuse it

    db_session.add(Strategy(user_id=user.id, name="Breakout"))
    with pytest.raises(IntegrityError, match="uq_strategies_user_id"):
        db_session.flush()


def test_version_numbers_are_unique_per_strategy(db_session, user):
    strategy = make_strategy(db_session, user)

    db_session.add(StrategyVersion(strategy_id=strategy.id, version=1, definition={}))
    with pytest.raises(IntegrityError, match="uq_strategy_versions_strategy_id"):
        db_session.flush()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE strategy_versions SET definition = '{}' WHERE strategy_id = :id",
        "DELETE FROM strategy_versions WHERE strategy_id = :id",
    ],
)
def test_versions_cannot_be_changed(db_session, user, statement):
    strategy = make_strategy(db_session, user)

    with pytest.raises(IntegrityError, match="strategy_versions is append-only"):
        db_session.execute(text(statement), {"id": strategy.id})


def test_trades_must_reference_an_existing_strategy(db_session, user):
    make_trade(db_session, user, strategy_id=make_strategy(db_session, user).id)

    with pytest.raises(IntegrityError, match="fk_trades_strategy_id_strategies"):
        make_trade(db_session, user, strategy_id=uuid.uuid4())
