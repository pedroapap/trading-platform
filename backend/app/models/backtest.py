import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import BacktestStatus, Direction, ExitReason
from app.market_data.timeframes import Timeframe
from app.models.base import PRICE as Price
from app.models.base import Base, enum_check, str_enum

PERCENT = Numeric(7, 4)


class Backtest(Base):
    """A strategy version run over one symbol's bars. The parameters are fixed when it is
    created; the run fills in the results."""

    __tablename__ = "backtests"
    __table_args__ = (
        # Versions are append-only, so the reference is a snapshot of the definition.
        ForeignKeyConstraint(
            ["strategy_id", "strategy_version"],
            ["strategy_versions.strategy_id", "strategy_versions.version"],
            ondelete="RESTRICT",
        ),
        enum_check("timeframe", Timeframe),
        enum_check("status", BacktestStatus),
        CheckConstraint("start_ts < end_ts", name="range_not_empty"),
        CheckConstraint("initial_capital > 0", name="initial_capital_positive"),
        CheckConstraint(
            "position_size_pct > 0 AND position_size_pct <= 100", name="position_size_in_range"
        ),
        CheckConstraint("fee_pct >= 0 AND fee_pct <= 10", name="fee_in_range"),
        CheckConstraint("slippage_pct >= 0 AND slippage_pct <= 10", name="slippage_in_range"),
        CheckConstraint("periods_per_year BETWEEN 1 AND 366", name="periods_per_year_in_range"),
        CheckConstraint(
            "status <> 'failed' OR error_message IS NOT NULL", name="failed_has_reason"
        ),
        CheckConstraint(
            "status <> 'completed' OR (metrics IS NOT NULL AND equity_curve IS NOT NULL)",
            name="completed_has_results",
        ),
        Index("ix_backtests_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    strategy_id: Mapped[uuid.UUID]
    strategy_version: Mapped[int]

    symbol: Mapped[str] = mapped_column(
        String(20), ForeignKey("instruments.symbol", ondelete="RESTRICT")
    )
    timeframe: Mapped[Timeframe] = mapped_column(str_enum(Timeframe, "timeframe"))
    # Requested bar start times, [start_ts, end_ts); None leaves that side open.
    start_ts: Mapped[datetime | None]
    end_ts: Mapped[datetime | None]

    initial_capital: Mapped[Decimal] = mapped_column(Price)
    position_size_pct: Mapped[Decimal] = mapped_column(PERCENT)
    fee_pct: Mapped[Decimal] = mapped_column(PERCENT)
    slippage_pct: Mapped[Decimal] = mapped_column(PERCENT)
    # Annualizes the Sharpe and Sortino ratios: 365 for crypto, 252 for stock exchanges.
    periods_per_year: Mapped[int]

    status: Mapped[BacktestStatus] = mapped_column(
        str_enum(BacktestStatus, "status"), server_default=BacktestStatus.PENDING.value
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    # The bars the run used: how many, their time range and a SHA-256 fingerprint.
    bars_count: Mapped[int | None]
    first_bar_ts: Mapped[datetime | None]
    last_bar_ts: Mapped[datetime | None]
    data_hash: Mapped[str | None] = mapped_column(String(64))

    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Downsampled for charts: [{"ts": ..., "equity": ...}, ...].
    equity_curve: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)

    # The insert's own time, not its transaction's, so creation order is exact.
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]


class BacktestTrade(Base):
    """One simulated round trip, numbered in the order the backtest made them."""

    __tablename__ = "backtest_trades"
    __table_args__ = (
        enum_check("direction", Direction),
        enum_check("exit_reason", ExitReason),
        CheckConstraint("number >= 1", name="number_positive"),
        CheckConstraint("entry_price > 0 AND exit_price > 0", name="prices_positive"),
        CheckConstraint("size > 0", name="size_positive"),
        CheckConstraint("exit_time >= entry_time", name="exit_not_before_entry"),
    )

    backtest_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("backtests.id", ondelete="CASCADE"), primary_key=True
    )
    number: Mapped[int] = mapped_column(primary_key=True)
    direction: Mapped[Direction] = mapped_column(str_enum(Direction, "direction"))
    entry_time: Mapped[datetime]
    entry_price: Mapped[Decimal] = mapped_column(Price)
    exit_time: Mapped[datetime]
    exit_price: Mapped[Decimal] = mapped_column(Price)
    size: Mapped[Decimal] = mapped_column(Price)
    entry_fee: Mapped[Decimal] = mapped_column(Price)
    exit_fee: Mapped[Decimal] = mapped_column(Price)
    # What slippage cost on both fills, in money.
    slippage: Mapped[Decimal] = mapped_column(Price)
    pnl: Mapped[Decimal] = mapped_column(Price)
    # Return on the entry notional, in percent, as for live trades.
    pnl_pct: Mapped[Decimal] = mapped_column(Numeric(12, 4))
    exit_reason: Mapped[ExitReason] = mapped_column(str_enum(ExitReason, "exit_reason"))
