import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.enums import TradeEvent, TradeStatus
from app.errors import NotFoundError
from app.models import Trade, TradeAuditLog
from app.schemas.trade import TradeCreate, TradeFilters
from app.services import trades, users
from tests.helpers import ENTRY_TIME, make_trade

NEW_TRADE = TradeCreate(
    symbol="btcusd",
    direction="long",
    entry_price="45000",
    entry_time="2026-01-05T14:30:00Z",
    entry_size="0.5",
    stop_loss="44000",
)


def count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def test_create_stores_the_trade_and_its_entry_event(db_session, user):
    trade = trades.create_trade(db_session, user, NEW_TRADE)

    assert trade.status is TradeStatus.OPEN
    assert trade.symbol == "BTCUSD"
    assert trade.entry_price == Decimal("45000")
    event = db_session.scalars(select(TradeAuditLog)).one()
    assert event.trade_id == trade.id
    assert event.event_type is TradeEvent.ENTRY
    assert event.changed_by == user.id
    assert event.old_values is None
    assert event.new_values["entry_price"] == "45000"
    assert event.new_values["stop_loss"] == "44000"
    assert event.new_values["entry_time"] == "2026-01-05T14:30:00+00:00"


def test_failed_audit_write_leaves_no_trade_behind(db_session, user, monkeypatch):
    def broken_record(*args, **kwargs):
        raise RuntimeError("audit storage unavailable")

    monkeypatch.setattr(trades, "_record", broken_record)

    with pytest.raises(RuntimeError):
        trades.create_trade(db_session, user, NEW_TRADE)

    assert count(db_session, Trade) == 0
    assert count(db_session, TradeAuditLog) == 0


def test_get_returns_own_trade(db_session, user):
    trade = trades.create_trade(db_session, user, NEW_TRADE)

    assert trades.get_trade(db_session, user, trade.id) is trade


def test_get_hides_missing_and_foreign_trades(db_session, user):
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    foreign = trades.create_trade(db_session, other, NEW_TRADE)

    with pytest.raises(NotFoundError):
        trades.get_trade(db_session, user, uuid.uuid4())
    with pytest.raises(NotFoundError):
        trades.get_trade(db_session, user, foreign.id)


@pytest.fixture
def journal(db_session, user):
    """Four trades on consecutive days (oldest first), one belonging to another user."""
    strategy_id = uuid.uuid4()
    day = timedelta(days=1)
    closed = {
        "status": TradeStatus.CLOSED,
        "exit_price": Decimal("110"),
        "exit_time": ENTRY_TIME + 2 * day,
        "pnl": Decimal("10"),
        "pnl_pct": Decimal("10"),
    }
    made = {
        "btc_closed": make_trade(db_session, user, **closed),
        "eth_open": make_trade(db_session, user, symbol="ETHUSD", entry_time=ENTRY_TIME + day),
        "btc_strategy": make_trade(
            db_session, user, strategy_id=strategy_id, entry_time=ENTRY_TIME + 2 * day
        ),
        "btc_latest": make_trade(db_session, user, entry_time=ENTRY_TIME + 3 * day),
    }
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    make_trade(db_session, other)
    return made | {"strategy_id": strategy_id}


def listed(db, user, **filters) -> tuple[list, int]:
    return trades.list_trades(db, user, TradeFilters(**filters))


def test_list_returns_own_trades_newest_first(db_session, user, journal):
    items, total = listed(db_session, user)

    assert total == 4
    assert [t.id for t in items] == [
        journal["btc_latest"].id,
        journal["btc_strategy"].id,
        journal["eth_open"].id,
        journal["btc_closed"].id,
    ]


def test_list_filters_by_symbol_status_and_strategy(db_session, user, journal):
    eth, _ = listed(db_session, user, symbol="ethusd")
    closed, _ = listed(db_session, user, status="closed")
    by_strategy, _ = listed(db_session, user, strategy_id=journal["strategy_id"])

    assert [t.id for t in eth] == [journal["eth_open"].id]
    assert [t.id for t in closed] == [journal["btc_closed"].id]
    assert [t.id for t in by_strategy] == [journal["btc_strategy"].id]


def test_list_filters_entry_time_as_half_open_range(db_session, user, journal):
    items, total = listed(
        db_session,
        user,
        entry_from=ENTRY_TIME + timedelta(days=1),
        entry_to=ENTRY_TIME + timedelta(days=3),
    )

    assert total == 2
    assert {t.id for t in items} == {journal["eth_open"].id, journal["btc_strategy"].id}


def test_list_paginates_but_reports_the_full_total(db_session, user, journal):
    items, total = listed(db_session, user, limit=2, offset=1)

    assert total == 4
    assert [t.id for t in items] == [journal["btc_strategy"].id, journal["eth_open"].id]
