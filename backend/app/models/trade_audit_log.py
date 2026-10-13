import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Identity, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import TradeEvent
from app.models.base import Base, enum_check, str_enum


class TradeAuditLog(Base):
    """Append-only history of trade changes; a database trigger rejects UPDATE/DELETE."""

    __tablename__ = "trade_audit_log"
    __table_args__ = (enum_check("event_type", TradeEvent),)

    # Monotonic id gives a reliable event order, even within one transaction.
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    trade_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("trades.id", ondelete="RESTRICT"), index=True
    )
    event_type: Mapped[TradeEvent] = mapped_column(str_enum(TradeEvent, "event_type"))
    old_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    changed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    change_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())
