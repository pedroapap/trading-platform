from datetime import timedelta

from app.services import users
from tests.helpers import ENTRY_TIME, make_closed_trade, make_strategy, make_trade


def closed_at(hour: int) -> dict:
    return {"exit_time": ENTRY_TIME + timedelta(hours=hour)}


def curves(client, auth_headers, **params) -> list[dict]:
    response = client.get("/api/analytics/equity", params=params, headers=auth_headers)
    assert response.status_code == 200, response.json()
    return response.json()["curves"]


def curve(client, auth_headers, **params) -> dict:
    """The only curve: make_closed_trade's BTCUSD and ETHUSD are both quoted in USD."""
    [usd] = curves(client, auth_headers, **params)
    assert usd["currency"] == "USD"
    return usd


def test_realized_pnl_accumulates_in_closing_order(client, auth_headers, db_session, user):
    # Inserted out of order: the curve follows closing times, not insertion.
    for hour, pnl in [(3, "3"), (1, "10"), (5, "20"), (2, "-15"), (4, "-2")]:
        make_closed_trade(db_session, user, pnl, **closed_at(hour))
    make_trade(db_session, user)  # still open: no realized P&L

    equity = curve(client, auth_headers)

    # Cumulative 10, -5, -2, -4, 16. The high of 10 falls to -5: a drawdown of 15.
    assert [(p["pnl"], p["cumulative_pnl"]) for p in equity["points"]] == [
        ("10", "10"),
        ("-15", "-5"),
        ("3", "-2"),
        ("-2", "-4"),
        ("20", "16"),
    ]
    assert [p["ts"] for p in equity["points"]] == sorted(p["ts"] for p in equity["points"])
    assert (equity["total_pnl"], equity["max_drawdown"]) == ("16", "15")


def test_a_first_loss_is_a_drawdown_from_zero(client, auth_headers, db_session, user):
    make_closed_trade(db_session, user, "-7", **closed_at(1))
    make_closed_trade(db_session, user, "5", **closed_at(2))

    equity = curve(client, auth_headers)

    assert (equity["total_pnl"], equity["max_drawdown"]) == ("-2", "7")


def test_the_curve_can_be_narrowed(client, auth_headers, db_session, user):
    strategy = make_strategy(db_session, user)
    make_closed_trade(db_session, user, "10", **closed_at(1))
    make_closed_trade(db_session, user, "20", symbol="ETHUSD", **closed_at(2))
    make_closed_trade(db_session, user, "30", strategy_id=strategy.id, **closed_at(3))

    def totals(**params) -> tuple[str, int]:
        equity = curve(client, auth_headers, **params)
        return equity["total_pnl"], len(equity["points"])

    assert totals(symbol="ethusd") == ("20", 1)
    assert totals(strategy_id=str(strategy.id)) == ("30", 1)
    assert totals(closed_from=(ENTRY_TIME + timedelta(hours=2)).isoformat()) == ("50", 2)
    assert totals(closed_to=(ENTRY_TIME + timedelta(hours=2)).isoformat()) == ("10", 1)


def test_without_closed_trades_there_is_no_curve(client, auth_headers, db_session):
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    make_closed_trade(db_session, other, "100")  # someone else's

    assert curves(client, auth_headers) == []


def test_each_quote_currency_has_its_own_curve(client, auth_headers, db_session, user):
    for hour, (symbol, pnl) in enumerate(
        [
            ("BTCUSDT", "50"),
            ("ETHBTC", "-0.02"),
            ("BTCUSDT", "-80"),
            ("AAPL", "5"),  # AAPL's currency isn't set
            ("ETHBTC", "0.05"),
            ("BTCUSDT", "40"),
            ("AAPL", "-8"),
        ],
        start=1,
    ):
        make_closed_trade(db_session, user, pnl, symbol=symbol, **closed_at(hour))

    btc, usdt, unset = curves(client, auth_headers)

    assert [p["cumulative_pnl"] for p in btc["points"]] == ["-0.02", "0.03"]
    assert [p["cumulative_pnl"] for p in usdt["points"]] == ["50", "-30", "10"]
    assert [p["cumulative_pnl"] for p in unset["points"]] == ["5", "-3"]
    assert [(c["currency"], c["total_pnl"], c["max_drawdown"]) for c in (btc, usdt, unset)] == [
        ("BTC", "0.03", "0.02"),
        ("USDT", "10", "80"),
        (None, "-3", "8"),
    ]
