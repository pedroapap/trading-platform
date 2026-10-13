import uuid

import pytest

from app.schemas.trade import TradeClose, TradeCreate
from app.services import trades, users

NEW_TRADE = {
    "symbol": "btcusd",
    "direction": "long",
    "entry_price": "45000",
    "entry_time": "2026-01-05T14:30:00Z",
    "entry_size": "0.5",
}


@pytest.fixture
def api(client, auth_headers):
    client.headers.update(auth_headers)
    return client


def create(api, **overrides) -> dict:
    response = api.post("/api/trades", json=NEW_TRADE | overrides)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_returns_the_trade(api):
    body = create(api, stop_loss=44000.5)

    assert body["symbol"] == "BTCUSD"
    assert body["status"] == "open"
    assert body["entry_price"] == "45000"
    assert body["stop_loss"] == "44000.5"
    assert body["pnl"] is None


def test_trade_endpoints_require_a_token(client):
    assert client.post("/api/trades", json=NEW_TRADE).status_code == 401
    assert client.get("/api/trades").status_code == 401


def test_create_validates_input(api):
    response = api.post("/api/trades", json=NEW_TRADE | {"entry_price": "-1"})

    assert response.status_code == 422


def test_list_filters_and_paginates(api):
    create(api)
    create(api, symbol="ETHUSD")

    page = api.get("/api/trades", params={"symbol": "ethusd", "limit": 10}).json()

    assert page["total"] == 1
    assert page["limit"] == 10
    assert [t["symbol"] for t in page["items"]] == ["ETHUSD"]


def test_list_rejects_unknown_filters(api):
    assert api.get("/api/trades", params={"colour": "red"}).status_code == 422


def test_get_returns_own_trade(api):
    trade = create(api)

    response = api.get(f"/api/trades/{trade['id']}")

    assert response.status_code == 200
    assert response.json() == trade


def test_get_unknown_foreign_or_malformed_ids(api, db_session):
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    foreign = trades.create_trade(db_session, other, TradeCreate(**NEW_TRADE))

    assert api.get(f"/api/trades/{uuid.uuid4()}").status_code == 404
    assert api.get(f"/api/trades/{foreign.id}").json() == {"detail": "Trade not found"}
    assert api.get("/api/trades/not-a-uuid").status_code == 422


def test_patch_updates_the_trade(api):
    trade = create(api)

    response = api.patch(f"/api/trades/{trade['id']}", json={"take_profit": "50000"})

    assert response.status_code == 200
    assert response.json()["take_profit"] == "50000"


def test_patch_rejects_exit_fields(api):
    trade = create(api)

    response = api.patch(f"/api/trades/{trade['id']}", json={"exit_price": "46000"})

    assert response.status_code == 422


def test_patch_of_a_closed_trade_is_a_conflict(api, db_session, user):
    trade = create(api)
    close = TradeClose(exit_price="46000", exit_time="2026-01-06T09:00:00Z")
    trades.close_trade(db_session, user, uuid.UUID(trade["id"]), close)

    response = api.patch(f"/api/trades/{trade['id']}", json={"take_profit": "50000"})

    assert response.status_code == 409
    assert response.json() == {"detail": "Cannot edit a closed trade"}
