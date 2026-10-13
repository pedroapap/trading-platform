from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.enums import TradeStatus
from tests.helpers import make_trade


def test_new_trade_gets_defaults(db_session, user):
    trade = make_trade(db_session, user)

    assert trade.status is TradeStatus.OPEN
    assert trade.entry_fee == Decimal("0")
    assert trade.exit_fee == Decimal("0")
    assert trade.leverage == Decimal("1")
    assert trade.pnl is None


@pytest.mark.parametrize(
    ("assignments", "constraint"),
    [
        ("direction = 'flat'", "ck_trades_direction"),
        ("status = 'pending'", "ck_trades_status"),
        ("entry_price = 0", "ck_trades_entry_price_positive"),
        ("entry_size = -1", "ck_trades_entry_size_positive"),
        ("entry_fee = -0.01", "ck_trades_entry_fee_non_negative"),
        ("leverage = 0.5", "ck_trades_leverage_at_least_one"),
        ("stop_loss = 0", "ck_trades_stop_loss_positive"),
        ("exit_price = 110", "ck_trades_exit_fields_only_when_closed"),
        ("status = 'closed'", "ck_trades_closed_trade_has_exit"),
        (
            "status = 'closed', exit_price = 110, exit_time = entry_time - interval '1 minute',"
            " pnl = 10, pnl_pct = 10",
            "ck_trades_exit_not_before_entry",
        ),
        (
            "status = 'closed', exit_price = 110, exit_time = entry_time, exit_size = 2,"
            " pnl = 10, pnl_pct = 10",
            "ck_trades_exit_size_in_range",
        ),
    ],
)
def test_database_rejects_invalid_trades(db_session, user, assignments, constraint):
    trade = make_trade(db_session, user)

    statement = text(f"UPDATE trades SET {assignments} WHERE id = :id")

    with pytest.raises(IntegrityError, match=constraint):
        db_session.execute(statement, {"id": trade.id})


def test_a_consistent_closed_trade_is_accepted(db_session, user):
    trade = make_trade(db_session, user)

    db_session.execute(
        text(
            "UPDATE trades SET status = 'closed', exit_price = 110, exit_time = entry_time,"
            " pnl = 10, pnl_pct = 10 WHERE id = :id"
        ),
        {"id": trade.id},
    )
