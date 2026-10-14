import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import Direction, TradeStatus
from app.models.base import PRICE as Price
from app.models.base import Base, TimestampMixin, enum_check, str_enum


class Trade(TimestampMixin, Base):
    """A manually logged trade: one entry, optionally closed by one exit."""

    __tablename__ = "trades"
    __table_args__ = (
        enum_check("direction", Direction),
        enum_check("status", TradeStatus),
        CheckConstraint("entry_price > 0", name="entry_price_positive"),
        CheckConstraint("entry_size > 0", name="entry_size_positive"),
        CheckConstraint("entry_fee >= 0", name="entry_fee_non_negative"),
        CheckConstraint("exit_price > 0", name="exit_price_positive"),
        CheckConstraint("exit_size > 0 AND exit_size <= entry_size", name="exit_size_in_range"),
        CheckConstraint("exit_fee >= 0", name="exit_fee_non_negative"),
        CheckConstraint("stop_loss > 0", name="stop_loss_positive"),
        CheckConstraint("take_profit > 0", name="take_profit_positive"),
        CheckConstraint("leverage >= 1", name="leverage_at_least_one"),
        CheckConstraint("exit_time >= entry_time", name="exit_not_before_entry"),
        CheckConstraint(
            "status = 'closed' OR (exit_price IS NULL AND exit_time IS NULL"
            " AND exit_size IS NULL AND pnl IS NULL AND pnl_pct IS NULL)",
            name="exit_fields_only_when_closed",
        ),
        CheckConstraint(
            "status <> 'closed' OR (exit_price IS NOT NULL AND exit_time IS NOT NULL"
            " AND pnl IS NOT NULL AND pnl_pct IS NOT NULL)",
            name="closed_trade_has_exit",
        ),
        CheckConstraint(
            "(strategy_id IS NULL) = (strategy_version IS NULL)",
            name="strategy_version_with_strategy",
        ),
        ForeignKeyConstraint(
            ["strategy_id", "strategy_version"],
            ["strategy_versions.strategy_id", "strategy_versions.version"],
            ondelete="RESTRICT",
        ),
        Index("ix_trades_user_id_entry_time", "user_id", "entry_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="RESTRICT")
    )
    # The version of the strategy the trade followed.
    strategy_version: Mapped[int | None]

    symbol: Mapped[str] = mapped_column(String(20))
    direction: Mapped[Direction] = mapped_column(str_enum(Direction, "direction"))
    status: Mapped[TradeStatus] = mapped_column(
        str_enum(TradeStatus, "status"), server_default=TradeStatus.OPEN.value
    )

    entry_price: Mapped[Decimal] = mapped_column(Price)
    entry_time: Mapped[datetime]
    entry_size: Mapped[Decimal] = mapped_column(Price)
    entry_fee: Mapped[Decimal] = mapped_column(Price, server_default=text("0"))

    exit_price: Mapped[Decimal | None] = mapped_column(Price)
    exit_time: Mapped[datetime | None]
    exit_size: Mapped[Decimal | None] = mapped_column(Price)
    exit_fee: Mapped[Decimal] = mapped_column(Price, server_default=text("0"))

    stop_loss: Mapped[Decimal | None] = mapped_column(Price)
    take_profit: Mapped[Decimal | None] = mapped_column(Price)
    leverage: Mapped[Decimal] = mapped_column(Numeric(10, 2), server_default=text("1"))

    pnl: Mapped[Decimal | None] = mapped_column(Price)
    # Return on the margin committed (notional / leverage), in percent.
    pnl_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
