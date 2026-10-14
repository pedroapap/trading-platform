from datetime import timedelta

import pytest

from app.enums import TradeStatus
from app.services import users
from tests.helpers import ENTRY_TIME, make_closed_trade, make_strategy, make_trade


@pytest.fixture
def trades(db_session, user):
    """Closed trades over two symbols and two strategies, plus trades that must not count."""
    breakout = make_strategy(db_session, user, "Breakout")
    reversion = make_strategy(db_session, user, "Mean reversion")
    for hour, (pnl, symbol, strategy) in enumerate(
        [
            ("100", "BTCUSD", breakout),
            ("-40", "BTCUSD", breakout),
            ("60", "ETHUSD", breakout),
            ("-20", "ETHUSD", reversion),
            ("10", "BTCUSD", None),
            ("0", "BTCUSD", breakout),  # breakeven: neither a win nor a loss
        ],
        start=1,
    ):
        make_closed_trade(
            db_session,
            user,
            pnl,
            symbol=symbol,
            strategy_id=strategy and strategy.id,
            exit_time=ENTRY_TIME + timedelta(hours=hour),
        )
    make_trade(db_session, user, strategy_id=breakout.id)  # still open
    make_trade(db_session, user, status=TradeStatus.CANCELLED)
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    make_closed_trade(db_session, other, "1000")
    return {"breakout": str(breakout.id), "reversion": str(reversion.id)}


def report(client, auth_headers, **params) -> list[dict]:
    response = client.get("/api/analytics/performance", params=params, headers=auth_headers)
    assert response.status_code == 200, response.json()
    return response.json()["groups"]


FIELDS = (
    "key",
    "label",
    "num_trades",
    "wins",
    "losses",
    "win_rate_pct",
    "total_pnl",
    "average_pnl",
)


def group(*values: object) -> dict:
    return dict(zip(FIELDS, values, strict=True))


def test_performance_by_symbol(client, auth_headers, trades):
    assert report(client, auth_headers, by="symbol") == [
        group("BTCUSD", "BTCUSD", 4, 2, 1, 50, "70", "17.5"),
        group("ETHUSD", "ETHUSD", 2, 1, 1, 50, "40", "20"),
    ]


def test_performance_by_strategy(client, auth_headers, trades):
    assert report(client, auth_headers, by="strategy") == [
        group(trades["breakout"], "Breakout", 4, 2, 1, 50, "120", "30"),
        group(None, None, 1, 1, 0, 100, "10", "10"),  # trades without a strategy
        group(trades["reversion"], "Mean reversion", 1, 0, 1, 0, "-20", "-20"),
    ]


def test_performance_over_a_closing_time_range(client, auth_headers, trades):
    # Closed at hours 2 to 4: -40 BTCUSD, +60 and -20 ETHUSD.
    closed_from = (ENTRY_TIME + timedelta(hours=2)).isoformat()
    closed_to = (ENTRY_TIME + timedelta(hours=5)).isoformat()

    groups = report(client, auth_headers, by="symbol", closed_from=closed_from, closed_to=closed_to)

    assert [(g["key"], g["num_trades"], g["total_pnl"]) for g in groups] == [
        ("ETHUSD", 2, "40"),
        ("BTCUSD", 1, "-40"),
    ]


def test_performance_needs_a_grouping(client, auth_headers):
    response = client.get("/api/analytics/performance", headers=auth_headers)

    assert response.status_code == 422


def test_analytics_require_a_token(client):
    assert client.get("/api/analytics/performance", params={"by": "symbol"}).status_code == 401
