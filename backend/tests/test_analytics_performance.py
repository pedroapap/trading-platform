from datetime import timedelta

import pytest

from app.enums import TradeStatus
from app.services import users
from tests.helpers import (
    ENTRY_TIME,
    make_closed_trade,
    make_journal_entry,
    make_strategy,
    make_trade,
)


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


@pytest.fixture
def journaled_trades(db_session, user):
    """Closed trades and the journal entries about them (only the trade matters, not the time)."""
    t1, t2, t3, t4, _unjournaled = (
        make_closed_trade(db_session, user, pnl) for pnl in ("100", "-40", "60", "-20", "10")
    )
    for trade, entry_type, emotion, tags in [
        (t1, "pre_trade", "calm", ["breakout", "plan"]),
        (t1, "post_trade", "confident", []),
        (t2, "pre_trade", "fomo", ["breakout", "late"]),
        (t2, "post_trade", "frustrated", ["late"]),  # the same tag again: counts once
        (t3, "pre_trade", "fomo", ["breakout"]),
        (t4, "post_trade", None, []),  # journaled, but no emotion or tag
        (None, "note", "calm", ["breakout"]),  # not about a trade
    ]:
        make_journal_entry(
            db_session,
            user,
            trade_id=trade and trade.id,
            entry_type=entry_type,
            emotion=emotion,
            tags=tags,
        )
    # The +10 trade has no journal entry at all; another user's journal never counts.
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    make_journal_entry(db_session, other, trade_id=make_closed_trade(db_session, other, "5").id)


def test_performance_by_emotion(client, auth_headers, journaled_trades):
    assert report(client, auth_headers, by="emotion") == [
        group("calm", "calm", 1, 1, 0, 100, "100", "100"),
        group("confident", "confident", 1, 1, 0, 100, "100", "100"),  # t1's other entry
        group("fomo", "fomo", 2, 1, 1, 50, "20", "10"),
        group(None, None, 2, 1, 1, 50, "-10", "-5"),  # t4 and the unjournaled trade
        group("frustrated", "frustrated", 1, 0, 1, 0, "-40", "-40"),
    ]


def test_performance_by_emotion_before_the_trade(client, auth_headers, journaled_trades):
    groups = report(client, auth_headers, by="emotion", entry_type="pre_trade")

    assert [(g["key"], g["num_trades"], g["total_pnl"]) for g in groups] == [
        ("calm", 1, "100"),
        ("fomo", 2, "20"),
        (None, 2, "-10"),
    ]


def test_performance_by_tag(client, auth_headers, journaled_trades):
    assert report(client, auth_headers, by="tag") == [
        group("breakout", "breakout", 3, 2, 1, pytest.approx(200 / 3), "120", "40"),
        group("plan", "plan", 1, 1, 0, 100, "100", "100"),
        group(None, None, 2, 1, 1, 50, "-10", "-5"),
        group("late", "late", 1, 0, 1, 0, "-40", "-40"),
    ]


def test_entry_type_only_applies_to_journal_groupings(client, auth_headers):
    params = {"by": "symbol", "entry_type": "pre_trade"}

    response = client.get("/api/analytics/performance", params=params, headers=auth_headers)

    assert response.status_code == 422
