import pytest

from app.security import create_access_token
from app.services import users
from tests.helpers import RSI_SWINGS, make_strategy, random_bars, store_bars


@pytest.fixture
def strategy_id(db_session, user) -> str:
    store_bars(db_session, random_bars(300))
    return str(make_strategy(db_session, user, definition=RSI_SWINGS).id)


def start_backtest(client, auth_headers, strategy_id, **fields):
    body = {"strategy_id": strategy_id, "symbol": "btcusd", "timeframe": "1m"} | fields
    return client.post("/api/backtests", json=body, headers=auth_headers)


def wait_for(client, auth_headers, backtest_id: str) -> dict:
    """Poll until the backtest has finished (the test client runs jobs before returning)."""
    for _ in range(20):
        backtest = client.get(f"/api/backtests/{backtest_id}", headers=auth_headers).json()
        if backtest["status"] in ("completed", "failed"):
            return backtest
    raise AssertionError(f"backtest {backtest_id} did not finish")


def test_a_backtest_runs_in_the_background(client, auth_headers, strategy_id):
    response = start_backtest(client, auth_headers, strategy_id, fee_pct="0.1")

    assert response.status_code == 202
    queued = response.json()
    assert queued["status"] == "pending"
    assert queued["metrics"] is None
    assert (queued["symbol"], queued["strategy_version"], queued["fee_pct"]) == ("BTCUSD", 1, "0.1")

    backtest = wait_for(client, auth_headers, queued["id"])
    assert backtest["status"] == "completed"
    assert backtest["bars_count"] == 300
    assert backtest["metrics"]["num_trades"] > 5
    assert set(backtest["metrics"]) >= {"total_return_pct", "max_drawdown_pct", "sharpe_ratio"}


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"symbol": "ETHUSD"}, "There are no ETHUSD bars in this range"),
        ({"strategy_version": 2}, "The strategy has no version 2"),
    ],
)
def test_a_backtest_needs_data_and_a_version(client, auth_headers, strategy_id, fields, message):
    response = start_backtest(client, auth_headers, strategy_id, **fields)

    assert (response.status_code, response.json()["detail"]) == (422, message)


def test_invalid_parameters_are_rejected_with_their_field(client, auth_headers, strategy_id):
    response = start_backtest(client, auth_headers, strategy_id, fee_pct="11")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "fee_pct"]


def test_another_users_backtest_is_not_found(client, auth_headers, db_session, strategy_id):
    backtest_id = start_backtest(client, auth_headers, strategy_id).json()["id"]
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    other_headers = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}

    response = client.get(f"/api/backtests/{backtest_id}", headers=other_headers)

    assert response.status_code == 404


def test_backtests_require_a_token(client):
    assert client.post("/api/backtests", json={}).status_code == 401
