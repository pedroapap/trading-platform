import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.enums import TradeEvent
from app.models import TradeAuditLog
from tests.helpers import make_trade


def add_event(db, trade, user, event=TradeEvent.ENTRY) -> TradeAuditLog:
    row = TradeAuditLog(
        trade_id=trade.id, event_type=event, new_values={"status": "open"}, changed_by=user.id
    )
    db.add(row)
    db.flush()
    db.refresh(row)
    return row


def test_events_are_ordered_and_timestamped(db_session, user):
    trade = make_trade(db_session, user)

    first = add_event(db_session, trade, user)
    second = add_event(db_session, trade, user, TradeEvent.EXIT)

    assert second.id > first.id
    assert second.created_at > first.created_at


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE trade_audit_log SET change_reason = 'rewritten' WHERE id = :id",
        "DELETE FROM trade_audit_log WHERE id = :id",
    ],
)
def test_events_cannot_be_changed_or_deleted(db_session, user, statement):
    event = add_event(db_session, make_trade(db_session, user), user)

    with pytest.raises(IntegrityError, match="append-only"):
        db_session.execute(text(statement), {"id": event.id})


def test_audit_log_cannot_be_truncated(db_session):
    with pytest.raises(IntegrityError, match="append-only"):
        db_session.execute(text("TRUNCATE trade_audit_log"))


def test_trade_with_history_cannot_be_deleted(db_session, user):
    trade = make_trade(db_session, user)
    add_event(db_session, trade, user)

    with pytest.raises(IntegrityError, match="fk_trade_audit_log_trade_id_trades"):
        db_session.execute(text("DELETE FROM trades WHERE id = :id"), {"id": trade.id})
