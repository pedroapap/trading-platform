"""Trades and their audit trail: every change is committed together with its audit row."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import TradeEvent
from app.errors import NotFoundError
from app.models import Trade, TradeAuditLog, User
from app.schemas.trade import TradeCreate

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
