"""Trades and their audit trail: every change is committed together with its audit row."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import TradeEvent, TradeStatus
from app.errors import ConflictError, InvalidOperationError, NotFoundError
from app.models import Trade, TradeAuditLog, User
from app.schemas.trade import TradeClose, TradeCreate, TradeFilters, TradeUpdate
from app.services.pnl import trade_pnl

ENTRY_FIELDS = (
    "symbol",
    "direction",
    "entry_price",
    "entry_time",
    "entry_size",
    "entry_fee",
    "stop_loss",
    "take_profit",
    "leverage",
    "strategy_id",
)
EXIT_FIELDS = ("status", "exit_price", "exit_time", "exit_size", "exit_fee", "pnl", "pnl_pct")


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


def _snapshot(trade: Trade, fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: _json_value(getattr(trade, field)) for field in fields}


def _record(
    db: Session,
    trade: Trade,
    user: User,
    event: TradeEvent,
    old: dict[str, Any] | None,
    new: dict[str, Any] | None,
    reason: str | None = None,
) -> None:
    db.add(
        TradeAuditLog(
            trade_id=trade.id,
            event_type=event,
            old_values=old,
            new_values=new,
            changed_by=user.id,
            change_reason=reason,
        )
    )


def create_trade(db: Session, user: User, data: TradeCreate) -> Trade:
    trade = Trade(user_id=user.id, **data.model_dump())
    try:
        db.add(trade)
        db.flush()  # assigns the id the audit row points to
        _record(db, trade, user, TradeEvent.ENTRY, None, _snapshot(trade, ENTRY_FIELDS))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return trade


def get_trade(db: Session, user: User, trade_id: uuid.UUID) -> Trade:
    trade = db.scalar(select(Trade).where(Trade.id == trade_id, Trade.user_id == user.id))
    if trade is None:
        raise NotFoundError("Trade not found")
    return trade


def list_trades(db: Session, user: User, filters: TradeFilters) -> tuple[list[Trade], int]:
    """Matching trades, newest entry first, plus the total count before pagination."""
    query = select(Trade).where(Trade.user_id == user.id)
    if filters.symbol is not None:
        query = query.where(Trade.symbol == filters.symbol)
    if filters.status is not None:
        query = query.where(Trade.status == filters.status)
    if filters.strategy_id is not None:
        query = query.where(Trade.strategy_id == filters.strategy_id)
    if filters.entry_from is not None:
        query = query.where(Trade.entry_time >= filters.entry_from)
    if filters.entry_to is not None:
        query = query.where(Trade.entry_time < filters.entry_to)

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    page = query.order_by(Trade.entry_time.desc(), Trade.id).limit(filters.limit)
    return list(db.scalars(page.offset(filters.offset))), total or 0


def _get_for_change(db: Session, user: User, trade_id: uuid.UUID) -> Trade:
    """Load and row-lock the trade so concurrent changes are applied one at a time."""
    query = select(Trade).where(Trade.id == trade_id, Trade.user_id == user.id)
    trade = db.scalar(query.with_for_update())
    if trade is None:
        raise NotFoundError("Trade not found")
    return trade


def _require_open(trade: Trade, action: str) -> None:
    if trade.status != TradeStatus.OPEN:
        raise ConflictError(f"Cannot {action} a {trade.status} trade")


def update_trade(db: Session, user: User, trade_id: uuid.UUID, data: TradeUpdate) -> Trade:
    """Correct an open trade's entry details; only fields that actually change are audited."""
    trade = _get_for_change(db, user, trade_id)
    _require_open(trade, "edit")
    changes = {
        field: value for field, value in data.changes().items() if getattr(trade, field) != value
    }
    if not changes:
        return trade
    old = {field: _json_value(getattr(trade, field)) for field in changes}
    new = {field: _json_value(value) for field, value in changes.items()}
    try:
        for field, value in changes.items():
            setattr(trade, field, value)
        _record(db, trade, user, TradeEvent.UPDATE, old, new)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return trade


def close_trade(db: Session, user: User, trade_id: uuid.UUID, data: TradeClose) -> Trade:
    trade = _get_for_change(db, user, trade_id)
    _require_open(trade, "close")
    if data.exit_time < trade.entry_time:
        raise InvalidOperationError("Exit time cannot be before the entry time")
    exit_size = trade.entry_size if data.exit_size is None else data.exit_size
    if exit_size > trade.entry_size:
        raise InvalidOperationError("Exit size cannot exceed the entry size")
    result = trade_pnl(
        trade.direction,
        trade.entry_price,
        trade.entry_size,
        data.exit_price,
        exit_size,
        trade.entry_fee,
        data.exit_fee,
        trade.leverage,
    )
    old = _snapshot(trade, EXIT_FIELDS)
    try:
        trade.status = TradeStatus.CLOSED
        trade.exit_price = data.exit_price
        trade.exit_time = data.exit_time
        trade.exit_size = exit_size
        trade.exit_fee = data.exit_fee
        trade.pnl = result.amount
        trade.pnl_pct = result.pct
        _record(db, trade, user, TradeEvent.EXIT, old, _snapshot(trade, EXIT_FIELDS))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return trade
