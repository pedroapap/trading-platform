"""Trades, backtests and comparisons name the quote currency of their money."""

import pytest

from app.enums import BacktestStatus
from tests.helpers import ENTRY_TIME, make_backtest, make_closed_trade, make_strategy

NEW_TRADE = {
    "symbol": "ETHBTC",
    "direction": "long",
    "entry_price": "0.05",
    "entry_time": "2026-01-05T14:30:00Z",
    "entry_size": "2",
}


@pytest.fixture
def api(client, auth_headers):
    class Api:
        def get(self, path, **kwargs):
            return client.get(f"/api{path}", headers=auth_headers, **kwargs)

        def send(self, method, path, json):
            response = client.request(method, f"/api{path}", headers=auth_headers, json=json)
            assert response.status_code in (200, 201), response.json()
            return response.json()

    return Api()


def test_a_trade_is_in_its_symbols_quote_currency(api):
    trade = api.send("POST", "/trades", NEW_TRADE)

    assert trade["quote_currency"] == "BTC"
    assert api.get(f"/trades/{trade['id']}").json()["quote_currency"] == "BTC"
    assert [t["quote_currency"] for t in api.get("/trades").json()["items"]] == ["BTC"]


def test_setting_a_currency_shows_on_the_symbols_trades(api):
    trade = api.send("POST", "/trades", NEW_TRADE | {"symbol": "AAPL"})
    assert trade["quote_currency"] is None

    api.send("PUT", "/instruments/AAPL", {"quote_currency": "USD"})

    assert api.get(f"/trades/{trade['id']}").json()["quote_currency"] == "USD"


def test_a_trade_moved_to_another_symbol_takes_its_currency(api):
    trade = api.send("POST", "/trades", NEW_TRADE)

    moved = api.send("PATCH", f"/trades/{trade['id']}", {"symbol": "ETHUSDT"})

    assert moved["quote_currency"] == "USDT"


def test_a_trade_corrected_to_another_symbol_takes_its_currency(api, db_session, user):
    trade = make_closed_trade(db_session, user, "5")
    assert api.get(f"/trades/{trade.id}").json()["quote_currency"] == "USD"

    corrected = api.send(
        "POST", f"/trades/{trade.id}/correct", {"symbol": "BTCEUR", "reason": "Wrong pair"}
    )

    assert corrected["quote_currency"] == "EUR"


def test_a_backtest_is_in_its_symbols_quote_currency(api, db_session, user):
    backtest = make_backtest(db_session, user, make_strategy(db_session, user))

    assert api.get(f"/backtests/{backtest.id}").json()["quote_currency"] == "USD"
    assert [b["quote_currency"] for b in api.get("/backtests").json()["items"]] == ["USD"]


def test_a_comparison_is_in_the_backtests_quote_currency(api, db_session, user):
    backtest = make_backtest(
        db_session,
        user,
        make_strategy(db_session, user),
        status=BacktestStatus.COMPLETED,
        metrics={},
        equity_curve=[],
        first_bar_ts=ENTRY_TIME,
        last_bar_ts=ENTRY_TIME,
    )

    comparison = api.get(f"/analytics/backtests/{backtest.id}/comparison").json()

    assert comparison["quote_currency"] == "USD"
