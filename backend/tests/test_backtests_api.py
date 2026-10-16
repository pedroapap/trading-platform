import pytest

from app.security import create_access_token
from app.services import users
from tests.helpers import (
    RSI_SWINGS,
    make_backtest,
    make_strategy,
    random_bars,
    store_bars,
    wait_for_backtest,
)


@pytest.fixture
def strategy_id(db_session, user) -> str:
    store_bars(db_session, random_bars(300))
    return str(make_strategy(db_session, user, definition=RSI_SWINGS).id)


def start_backtest(client, auth_headers, strategy_id, **fields):
    body = {"strategy_id": strategy_id, "symbol": "btcusd", "timeframe": "1m"} | fields
    return client.post("/api/backtests", json=body, headers=auth_headers)


def test_a_backtest_runs_in_the_background(client, auth_headers, strategy_id):
    response = start_backtest(client, auth_headers, strategy_id, fee_pct="0.1")

    assert response.status_code == 202
    queued = response.json()
    assert queued["status"] == "pending"
    assert queued["metrics"] is None
    assert (queued["symbol"], queued["strategy_version"], queued["fee_pct"]) == ("BTCUSD", 1, "0.1")

    backtest = wait_for_backtest(client, auth_headers, queued["id"])
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


def test_a_backtest_can_settle_inside_bars_with_finer_ones(client, auth_headers, strategy_id):
    response = start_backtest(
        client, auth_headers, strategy_id, timeframe="5m", detail_timeframe="1m"
    )

    backtest = wait_for_backtest(client, auth_headers, response.json()["id"])
    assert (backtest["status"], backtest["detail_timeframe"]) == ("completed", "1m")


def test_a_backtest_reports_its_out_of_sample_bars_apart(client, auth_headers, strategy_id):
    # 300 minute bars from 14:30: the last 100 are out-of-sample.
    response = start_backtest(
        client, auth_headers, strategy_id, out_of_sample_from="2026-01-05T17:50:00Z"
    )

    backtest = wait_for_backtest(client, auth_headers, response.json()["id"])
    split = backtest["split_metrics"]
    assert backtest["out_of_sample_from"] == "2026-01-05T17:50:00Z"
    assert (
        split["in_sample"]["num_trades"] + split["out_of_sample"]["num_trades"]
        == (backtest["metrics"]["num_trades"])
    )
    assert split["out_of_sample"]["num_trades"] > 0


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"out_of_sample_from": "2026-01-06T00:00:00Z"}, "bars on both sides"),
        (
            {"start": "2026-01-05T15:00:00Z", "out_of_sample_from": "2026-01-05T15:00:00Z"},
            "out_of_sample_from must be between start and end",
        ),
    ],
)
def test_an_out_of_sample_start_must_split_the_bars(
    client, auth_headers, strategy_id, fields, message
):
    response = start_backtest(client, auth_headers, strategy_id, **fields)

    assert response.status_code == 422
    assert message in str(response.json()["detail"])


def test_finer_bars_must_be_finer(client, auth_headers, strategy_id):
    response = start_backtest(client, auth_headers, strategy_id, detail_timeframe="5m")

    assert response.status_code == 422
    assert "detail_timeframe must be finer than timeframe" in response.json()["detail"][0]["msg"]


def test_a_backtest_can_borrow_up_to_ten_times_its_equity(client, auth_headers, strategy_id):
    response = start_backtest(client, auth_headers, strategy_id, position_size_pct="400")

    backtest = wait_for_backtest(client, auth_headers, response.json()["id"])
    assert (backtest["status"], backtest["position_size_pct"]) == ("completed", "400")
    too_much = start_backtest(client, auth_headers, strategy_id, position_size_pct="1000.5")
    assert too_much.status_code == 422
    assert too_much.json()["detail"][0]["loc"] == ["body", "position_size_pct"]


def test_invalid_parameters_are_rejected_with_their_field(client, auth_headers, strategy_id):
    response = start_backtest(client, auth_headers, strategy_id, fee_pct="11")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "fee_pct"]


@pytest.mark.parametrize("path", ["", "/trades", "/equity"])
def test_another_users_backtest_is_not_found(client, auth_headers, db_session, strategy_id, path):
    backtest_id = start_backtest(client, auth_headers, strategy_id).json()["id"]
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    other_headers = {"Authorization": f"Bearer {create_access_token(str(other.id))}"}

    response = client.get(f"/api/backtests/{backtest_id}{path}", headers=other_headers)

    assert response.status_code == 404
    listed = client.get("/api/backtests", headers=other_headers).json()
    assert listed["total"] == 0


def test_backtests_require_a_token(client):
    assert client.post("/api/backtests", json={}).status_code == 401


def test_backtests_are_listed_newest_first(client, auth_headers, db_session, user, strategy_id):
    other_strategy = str(make_strategy(db_session, user, "Other", definition=RSI_SWINGS).id)
    first, second, third = (
        start_backtest(client, auth_headers, strategy).json()["id"]
        for strategy in (strategy_id, other_strategy, strategy_id)
    )

    def listed(**params) -> tuple[list[str], int]:
        page = client.get("/api/backtests", params=params, headers=auth_headers).json()
        return [item["id"] for item in page["items"]], page["total"]

    assert listed() == ([third, second, first], 3)
    assert listed(strategy_id=strategy_id) == ([third, first], 2)
    assert listed(limit=1, offset=1) == ([second], 3)


def test_trades_are_listed_in_the_order_they_were_made(client, auth_headers, strategy_id):
    backtest = wait_for_backtest(
        client, auth_headers, start_backtest(client, auth_headers, strategy_id).json()["id"]
    )
    trades_url = f"/api/backtests/{backtest['id']}/trades"

    page = client.get(trades_url, headers=auth_headers).json()
    later = client.get(trades_url, params={"limit": 2, "offset": 2}, headers=auth_headers).json()

    count = backtest["metrics"]["num_trades"]
    assert page["total"] == count
    assert [trade["number"] for trade in page["items"]] == list(range(1, count + 1))
    assert [trade["number"] for trade in later["items"]] == [3, 4]
    first = page["items"][0]
    assert first["direction"] == "long"
    assert first["exit_reason"] in {"signal", "stop_loss", "take_profit", "end_of_data"}
    assert isinstance(first["pnl"], str)  # exact decimals, like other money amounts


def test_the_equity_curve_starts_at_the_initial_capital(client, auth_headers, strategy_id):
    backtest = wait_for_backtest(
        client, auth_headers, start_backtest(client, auth_headers, strategy_id).json()["id"]
    )

    curve = client.get(f"/api/backtests/{backtest['id']}/equity", headers=auth_headers).json()

    assert len(curve) == backtest["bars_count"]  # 300 points: under the 1,000-point limit
    assert (curve[0]["ts"], curve[0]["equity"]) == (backtest["first_bar_ts"], 10_000)
    assert curve[-1]["ts"] == backtest["last_bar_ts"]
    # Buy and hold beside it: ending where its return says.
    final = 10_000 * (1 + backtest["metrics"]["buy_and_hold_return_pct"] / 100)
    assert curve[-1]["benchmark"] == pytest.approx(final)


def test_an_equity_curve_stored_before_buy_and_hold_still_reads(
    client, auth_headers, db_session, user
):
    strategy = make_strategy(db_session, user)
    point = {"ts": "2026-01-05T14:30:00Z", "equity": 10_000.0}
    backtest = make_backtest(
        db_session, user, strategy, status="completed", metrics={}, equity_curve=[point]
    )

    curve = client.get(f"/api/backtests/{backtest.id}/equity", headers=auth_headers).json()

    assert curve == [point | {"benchmark": None}]


def test_a_pending_backtest_has_no_results_yet(client, auth_headers, db_session, user):
    pending = make_backtest(db_session, user, make_strategy(db_session, user))

    trades = client.get(f"/api/backtests/{pending.id}/trades", headers=auth_headers).json()
    curve = client.get(f"/api/backtests/{pending.id}/equity", headers=auth_headers).json()

    assert (trades["items"], trades["total"], curve) == ([], 0, [])
