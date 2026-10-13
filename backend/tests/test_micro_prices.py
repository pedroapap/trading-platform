"""Micro-priced coins (e.g. SHIB) keep all 12 decimals end to end."""

import io

from app.services.market_data import import_bars

SHIB_BARS = (
    "timestamp,open,high,low,close,volume\n"
    "2026-01-05T00:00Z,0.000012345678,0.000012400001,0.000012300002,0.000012399999,1500000000\n"
    "2026-01-05T00:01Z,0.000012399999,0.000012500000,0.000012399990,0.000012456789,1250000000\n"
)


def test_micro_prices_round_trip_through_import_and_the_bars_api(db_session, client, auth_headers):
    import_bars(db_session, io.StringIO(SHIB_BARS), "SHIBUSDT")

    body = client.get(
        "/api/market-data/SHIBUSDT/bars", params={"timeframe": "1m"}, headers=auth_headers
    ).json()

    assert [bar["open"] for bar in body["bars"]] == ["0.000012345678", "0.000012399999"]
    assert body["bars"][1]["close"] == "0.000012456789"


def test_micro_prices_round_trip_through_trades(client, auth_headers):
    trade = client.post(
        "/api/trades",
        json={
            "symbol": "SHIBUSDT",
            "direction": "long",
            "entry_price": "0.000012345678",
            "entry_time": "2026-01-05T00:00:00Z",
            "entry_size": "1000000",
        },
        headers=auth_headers,
    ).json()

    closed = client.post(
        f"/api/trades/{trade['id']}/close",
        json={"exit_price": "0.000013", "exit_time": "2026-01-06T00:00:00Z"},
        headers=auth_headers,
    ).json()

    assert trade["entry_price"] == "0.000012345678"
    assert closed["pnl"] == "0.654322"
