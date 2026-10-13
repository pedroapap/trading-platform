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


EXIT = {"exit_price": "46000", "exit_time": "2026-01-06T09:00:00Z", "exit_fee": "5"}


def test_close_returns_the_closed_trade_with_pnl(api):
    trade = create(api)

    response = api.post(f"/api/trades/{trade['id']}/close", json=EXIT)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "closed"
    assert body["exit_size"] == "0.5"
    assert body["pnl"] == "495"
    assert body["pnl_pct"] == "2.2"


def test_close_rejects_an_exit_before_the_entry(api):
    trade = create(api)
    early = EXIT | {"exit_time": "2026-01-05T14:00:00Z"}

    response = api.post(f"/api/trades/{trade['id']}/close", json=early)

    assert response.status_code == 422
    assert response.json() == {"detail": "Exit time cannot be before the entry time"}


def test_close_unknown_trade_is_not_found(api):
    assert api.post(f"/api/trades/{uuid.uuid4()}/close", json=EXIT).status_code == 404


def test_cancel_works_with_or_without_a_reason(api):
    first, second = create(api), create(api)

    plain = api.post(f"/api/trades/{first['id']}/cancel")
    with_reason = api.post(f"/api/trades/{second['id']}/cancel", json={"reason": "Not filled"})

    assert plain.status_code == 200
    assert plain.json()["status"] == "cancelled"
    assert with_reason.status_code == 200


@pytest.mark.parametrize("action", ["close", "cancel"])
def test_finished_trades_cannot_change_status_again(api, action):
    trade = create(api)
    api.post(f"/api/trades/{trade['id']}/close", json=EXIT)

    body = EXIT if action == "close" else None
    response = api.post(f"/api/trades/{trade['id']}/{action}", json=body)

    assert response.status_code == 409
    assert response.json() == {"detail": f"Cannot {action} a closed trade"}


def test_audit_log_lists_events_oldest_first(api, user):
    trade = create(api)
    api.patch(f"/api/trades/{trade['id']}", json={"stop_loss": "44000"})
    api.post(f"/api/trades/{trade['id']}/close", json=EXIT)

    response = api.get(f"/api/trades/{trade['id']}/audit-log")

    assert response.status_code == 200
    log = response.json()
    assert [e["event_type"] for e in log] == ["entry", "update", "exit"]
    assert log[1]["old_values"] == {"stop_loss": None}
    assert log[1]["new_values"] == {"stop_loss": "44000"}
    assert log[2]["new_values"]["pnl"] == "495"
    assert all(e["changed_by"] == str(user.id) for e in log)


def test_audit_log_of_a_create_then_close_has_two_events(api):
    trade = create(api)
    api.post(f"/api/trades/{trade['id']}/close", json=EXIT)

    log = api.get(f"/api/trades/{trade['id']}/audit-log").json()

    assert [e["event_type"] for e in log] == ["entry", "exit"]
    assert log[0]["created_at"] < log[1]["created_at"]


def test_audit_log_of_an_unknown_trade_is_not_found(api):
    assert api.get(f"/api/trades/{uuid.uuid4()}/audit-log").status_code == 404


def test_correct_a_closed_trade(api):
    trade = create(api)
    api.post(f"/api/trades/{trade['id']}/close", json=EXIT)

    response = api.post(
        f"/api/trades/{trade['id']}/correct",
        json={"exit_price": "46100", "reason": "Wrong fill price"},
    )

    assert response.status_code == 200
    assert response.json()["pnl"] == "545"
    correction = api.get(f"/api/trades/{trade['id']}/audit-log").json()[-1]
    assert correction["event_type"] == "correction"
    assert correction["change_reason"] == "Wrong fill price"


def test_correction_needs_a_reason(api):
    trade = create(api)
    api.post(f"/api/trades/{trade['id']}/close", json=EXIT)

    response = api.post(f"/api/trades/{trade['id']}/correct", json={"exit_price": "46100"})

    assert response.status_code == 422


def test_open_trades_are_edited_not_corrected(api):
    trade = create(api)

    response = api.post(
        f"/api/trades/{trade['id']}/correct", json={"entry_price": "1", "reason": "Typo"}
    )

    assert response.status_code == 409
