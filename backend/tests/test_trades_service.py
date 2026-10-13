import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.enums import TradeEvent, TradeStatus
from app.errors import NotFoundError
from app.models import Trade, TradeAuditLog
from app.schemas.trade import TradeCreate
from app.services import trades, users

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
