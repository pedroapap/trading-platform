from pathlib import Path

import pytest

from app.services.market_data import import_bars

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def api(client, auth_headers, db_session):
    with (FIXTURES / "binance_1m.csv").open() as stream:
        import_bars(db_session, stream, "BTCUSDT")
    client.headers.update(auth_headers)
    return client


def bars(api, symbol="btcusdt", **params) -> list[dict]:
    response = api.get(f"/api/market-data/{symbol}/bars", params={"timeframe": "1m"} | params)
    assert response.status_code == 200, response.text
    return response.json()["bars"]


def test_bars_are_returned_oldest_first_with_exact_values(api):
    result = bars(api)

    assert [bar["ts"] for bar in result] == [
        "2026-01-05T00:00:00Z",
        "2026-01-05T00:01:00Z",
        "2026-01-05T00:02:00Z",
    ]
    assert result[0] | {"ts": None} == {
        "ts": None,
        "open": "93000.5",
        "high": "93010",
        "low": "92990.1",
        "close": "93005",
        "volume": "12.5",
    }


def test_range_is_half_open_and_limit_pages(api):
    in_range = bars(api, start="2026-01-05T00:01:00Z", end="2026-01-05T00:02:00Z")
    first_two = bars(api, limit=2)

    assert [bar["ts"] for bar in in_range] == ["2026-01-05T00:01:00Z"]
    assert len(first_two) == 2


def test_unknown_symbols_are_empty(api):
    assert bars(api, symbol="ETHUSDT") == []


def test_a_symbol_may_contain_a_slash(api, db_session):
    with (FIXTURES / "binance_1m.csv").open() as stream:
        import_bars(db_session, stream, "BTC/USDT")

    # Starlette decodes %2F before routing, so both spellings reach the same route.
    for symbol in ("btc/usdt", "BTC%2FUSDT"):
        response = api.get(f"/api/market-data/{symbol}/bars", params={"timeframe": "1m"})
        assert response.status_code == 200, response.text
        assert response.json()["symbol"] == "BTC/USDT"
        assert len(response.json()["bars"]) == 3


def test_query_is_validated(api):
    assert api.get("/api/market-data/BTCUSDT/bars").status_code == 422
    assert api.get("/api/market-data/BTCUSDT/bars?timeframe=2m").status_code == 422
    assert api.get("/api/market-data/BTC%20USDT/bars?timeframe=1m").status_code == 422


def test_bars_require_a_token(client):
    assert client.get("/api/market-data/BTCUSDT/bars?timeframe=1m").status_code == 401
