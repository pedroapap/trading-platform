import pytest

from app.services import instruments


@pytest.fixture
def registered(db_session):
    for symbol in ("ETHBTC", "AAPL", "BTCUSDT"):
        instruments.register(db_session, symbol)


def listed(client, auth_headers) -> list[dict]:
    response = client.get("/api/instruments", headers=auth_headers)
    assert response.status_code == 200, response.json()
    return response.json()


def test_instruments_are_listed_by_symbol(client, auth_headers, registered):
    assert listed(client, auth_headers) == [
        {"symbol": "AAPL", "quote_currency": None},
        {"symbol": "BTCUSDT", "quote_currency": "USDT"},
        {"symbol": "ETHBTC", "quote_currency": "BTC"},
    ]


def test_a_quote_currency_is_set_or_replaced(client, auth_headers, registered):
    for symbol, currency in (("aapl", "usd"), ("BTCUSDT", "USDC")):
        response = client.put(
            f"/api/instruments/{symbol}", headers=auth_headers, json={"quote_currency": currency}
        )
        assert response.status_code == 200, response.json()

    assert listed(client, auth_headers) == [
        {"symbol": "AAPL", "quote_currency": "USD"},
        {"symbol": "BTCUSDT", "quote_currency": "USDC"},
        {"symbol": "ETHBTC", "quote_currency": "BTC"},
    ]


def test_setting_a_quote_currency_registers_a_new_symbol(client, auth_headers):
    response = client.put(
        "/api/instruments/btc/usdt", headers=auth_headers, json={"quote_currency": "USDT"}
    )

    assert response.status_code == 200, response.json()
    assert response.json() == {"symbol": "BTC/USDT", "quote_currency": "USDT"}
    assert listed(client, auth_headers) == [{"symbol": "BTC/USDT", "quote_currency": "USDT"}]


@pytest.mark.parametrize(
    ("symbol", "body"),
    [
        ("AAPL", {"quote_currency": "US DOLLAR"}),
        ("AAPL", {"quote_currency": "U"}),
        ("AAPL", {}),
        ("AAPL", {"quote_currency": "USD", "base_currency": "AAPL"}),
        ("NOT A SYMBOL", {"quote_currency": "USD"}),
    ],
)
def test_invalid_codes_and_symbols_are_rejected(client, auth_headers, symbol, body):
    response = client.put(f"/api/instruments/{symbol}", headers=auth_headers, json=body)

    assert response.status_code == 422


def test_instruments_need_a_login(client):
    assert client.get("/api/instruments").status_code == 401
    assert client.put("/api/instruments/AAPL", json={"quote_currency": "USD"}).status_code == 401
