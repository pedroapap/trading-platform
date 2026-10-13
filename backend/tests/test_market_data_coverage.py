from pathlib import Path

from app.services.market_data import import_bars

FIXTURES = Path(__file__).parent / "fixtures"


def test_coverage_lists_each_symbol_and_timeframe(db_session, client, auth_headers):
    for name, symbol in [
        ("daily_yahoo.csv", "BTCUSDT"),
        ("binance_1m.csv", "BTCUSDT"),
        ("daily_generic.csv", "AAPL"),
    ]:
        with (FIXTURES / name).open() as stream:
            import_bars(db_session, stream, symbol)

    response = client.get("/api/market-data/symbols", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == [
        {
            "symbol": "AAPL",
            "timeframe": "1d",
            "first_ts": "2026-01-05T00:00:00Z",
            "last_ts": "2026-01-07T00:00:00Z",
            "bars": 3,
        },
        {
            "symbol": "BTCUSDT",
            "timeframe": "1m",
            "first_ts": "2026-01-05T00:00:00Z",
            "last_ts": "2026-01-05T00:02:00Z",
            "bars": 3,
        },
        {
            "symbol": "BTCUSDT",
            "timeframe": "1d",
            "first_ts": "2026-01-05T00:00:00Z",
            "last_ts": "2026-01-07T00:00:00Z",
            "bars": 3,
        },
    ]


def test_coverage_is_empty_without_data(client, auth_headers):
    assert client.get("/api/market-data/symbols", headers=auth_headers).json() == []


def test_coverage_requires_a_token(client):
    assert client.get("/api/market-data/symbols").status_code == 401
