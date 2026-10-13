import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.enums import Direction, TradeEvent, TradeStatus
from app.errors import ConflictError, InvalidOperationError, NotFoundError
from app.models import Trade, TradeAuditLog
from app.schemas.trade import TradeClose, TradeCreate, TradeFilters, TradeUpdate
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


def events(db, trade) -> list[TradeAuditLog]:
    query = select(TradeAuditLog).where(TradeAuditLog.trade_id == trade.id)
    return list(db.scalars(query.order_by(TradeAuditLog.id)))


def test_update_applies_and_audits_only_real_changes(db_session, user):
    trade = trades.create_trade(db_session, user, NEW_TRADE)
    update = TradeUpdate(entry_price="45000.00", stop_loss="44500", take_profit="50000")

    updated = trades.update_trade(db_session, user, trade.id, update)

    assert updated.stop_loss == Decimal("44500")
    assert updated.take_profit == Decimal("50000")
    change = events(db_session, trade)[-1]
    assert change.event_type is TradeEvent.UPDATE
    # entry_price is numerically unchanged, so it is not recorded
    assert change.old_values == {"stop_loss": "44000", "take_profit": None}
    assert change.new_values == {"stop_loss": "44500", "take_profit": "50000"}


def test_update_can_clear_optional_fields(db_session, user):
    trade = trades.create_trade(db_session, user, NEW_TRADE)

    trades.update_trade(db_session, user, trade.id, TradeUpdate(stop_loss=None))

    assert trade.stop_loss is None
    assert events(db_session, trade)[-1].new_values == {"stop_loss": None}


def test_update_without_changes_writes_no_event(db_session, user):
    trade = trades.create_trade(db_session, user, NEW_TRADE)

    trades.update_trade(db_session, user, trade.id, TradeUpdate(symbol="BTCUSD"))

    assert [e.event_type for e in events(db_session, trade)] == [TradeEvent.ENTRY]


@pytest.mark.parametrize("status", [TradeStatus.CLOSED, TradeStatus.CANCELLED])
def test_update_of_a_finished_trade_is_a_conflict(db_session, user, status):
    finished = {"status": status}
    if status is TradeStatus.CLOSED:
        finished |= {
            "exit_price": Decimal("110"),
            "exit_time": ENTRY_TIME,
            "pnl": Decimal("10"),
            "pnl_pct": Decimal("10"),
        }
    trade = make_trade(db_session, user, **finished)

    with pytest.raises(ConflictError, match=f"Cannot edit a {status} trade"):
        trades.update_trade(db_session, user, trade.id, TradeUpdate(stop_loss="90"))


def test_update_of_a_foreign_trade_is_not_found(db_session, user):
    other = users.create_user(db_session, "other@example.com", "another-long-password")
    foreign = trades.create_trade(db_session, other, NEW_TRADE)

    with pytest.raises(NotFoundError):
        trades.update_trade(db_session, user, foreign.id, TradeUpdate(stop_loss="90"))


def exit_at(price: str, **fields) -> TradeClose:
    return TradeClose(exit_price=price, exit_time="2026-01-06T09:00:00Z", **fields)


def test_close_records_exit_and_pnl(db_session, user):
    trade = trades.create_trade(db_session, user, NEW_TRADE)  # long 0.5 @ 45000

    closed = trades.close_trade(db_session, user, trade.id, exit_at("46000", exit_fee="5"))

    assert closed.status is TradeStatus.CLOSED
    assert closed.exit_size == Decimal("0.5")  # defaults to the full position
    assert closed.pnl == Decimal("495")  # 0.5 * 1000 - 5
    assert closed.pnl_pct == Decimal("2.2")  # 495 / 22500
    exit_event = events(db_session, trade)[-1]
    assert exit_event.event_type is TradeEvent.EXIT
    assert exit_event.old_values["status"] == "open"
    assert exit_event.old_values["pnl"] is None
    assert exit_event.new_values == {
        "status": "closed",
        "exit_price": "46000",
        "exit_time": "2026-01-06T09:00:00+00:00",
        "exit_size": "0.5",
        "exit_fee": "5",
        "pnl": "495",
        "pnl_pct": "2.2",
    }


def test_close_short_partially(db_session, user):
    short = NEW_TRADE.model_copy(update={"direction": Direction.SHORT})
    trade = trades.create_trade(db_session, user, short)

    closed = trades.close_trade(db_session, user, trade.id, exit_at("44000", exit_size="0.25"))

    assert closed.pnl == Decimal("250")
    assert closed.exit_size == Decimal("0.25")


@pytest.mark.parametrize(
    ("close", "message"),
    [
        (
            TradeClose(exit_price="46000", exit_time="2026-01-05T14:29:59Z"),
            "Exit time cannot be before the entry time",
        ),
        (exit_at("46000", exit_size="0.6"), "Exit size cannot exceed the entry size"),
    ],
)
def test_close_rejects_exits_inconsistent_with_the_entry(db_session, user, close, message):
    trade = trades.create_trade(db_session, user, NEW_TRADE)

    with pytest.raises(InvalidOperationError, match=message):
        trades.close_trade(db_session, user, trade.id, close)

    assert trade.status is TradeStatus.OPEN
    assert len(events(db_session, trade)) == 1


def test_closing_twice_is_a_conflict(db_session, user):
    trade = trades.create_trade(db_session, user, NEW_TRADE)
    trades.close_trade(db_session, user, trade.id, exit_at("46000"))

    with pytest.raises(ConflictError, match="Cannot close a closed trade"):
        trades.close_trade(db_session, user, trade.id, exit_at("47000"))
