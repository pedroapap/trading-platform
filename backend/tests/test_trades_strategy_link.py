"""Trades may reference only the caller's own strategies."""

import uuid

import pytest

from app.services import users
from tests.helpers import make_strategy

TRADE = {
    "symbol": "BTCUSD",
    "direction": "long",
    "entry_price": "45000",
    "entry_time": "2026-01-05T14:30:00Z",
    "entry_size": "0.5",
}
EXIT = {"exit_price": "46000", "exit_time": "2026-01-06T09:00:00Z"}


@pytest.fixture
def api(client, auth_headers):
    client.headers.update(auth_headers)
    return client


@pytest.fixture
def foreign_strategy(db_session):
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    return make_strategy(db_session, other, name="Theirs")


def test_a_trade_can_follow_an_own_strategy(api, db_session, user):
    strategy = make_strategy(db_session, user)

    response = api.post("/api/trades", json=TRADE | {"strategy_id": str(strategy.id)})

    assert response.status_code == 201
    assert response.json()["strategy_id"] == str(strategy.id)


@pytest.mark.parametrize("which", ["foreign", "unknown"])
def test_create_rejects_strategies_that_are_not_the_users(api, foreign_strategy, which):
    strategy_id = foreign_strategy.id if which == "foreign" else uuid.uuid4()

    response = api.post("/api/trades", json=TRADE | {"strategy_id": str(strategy_id)})

    assert response.status_code == 422
    assert response.json() == {"detail": "Unknown strategy"}


def test_update_and_correct_reject_foreign_strategies(api, foreign_strategy):
    open_trade = api.post("/api/trades", json=TRADE).json()
    closed_trade = api.post("/api/trades", json=TRADE).json()
    api.post(f"/api/trades/{closed_trade['id']}/close", json=EXIT)
    foreign = str(foreign_strategy.id)

    edited = api.patch(f"/api/trades/{open_trade['id']}", json={"strategy_id": foreign})
    corrected = api.post(
        f"/api/trades/{closed_trade['id']}/correct",
        json={"strategy_id": foreign, "reason": "Wrong strategy"},
    )

    assert edited.status_code == 422
    assert corrected.status_code == 422


def test_the_strategy_link_can_be_cleared(api, db_session, user):
    strategy = make_strategy(db_session, user)
    trade = api.post("/api/trades", json=TRADE | {"strategy_id": str(strategy.id)}).json()

    response = api.patch(f"/api/trades/{trade['id']}", json={"strategy_id": None})

    assert response.json()["strategy_id"] is None
