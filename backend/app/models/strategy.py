import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, foreign, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Strategy(TimestampMixin, Base):
    """A named strategy; its rules live in immutable, numbered versions."""

    __tablename__ = "strategies"
    __table_args__ = (UniqueConstraint("user_id", "name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    current_version: Mapped[int] = mapped_column(server_default=text("1"))

    # The version whose definition is in force, loaded together with the strategy.
    current: Mapped["StrategyVersion"] = relationship(
        primaryjoin=lambda: (
            (Strategy.id == foreign(StrategyVersion.strategy_id))
            & (Strategy.current_version == foreign(StrategyVersion.version))
        ),
        viewonly=True,
        lazy="joined",
    )


class StrategyVersion(Base):
    """One saved definition of a strategy. A database trigger rejects UPDATE/DELETE, so a
    backtest that names a version can always be reproduced."""

    __tablename__ = "strategy_versions"
    __table_args__ = (
        UniqueConstraint("strategy_id", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    strategy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("strategies.id", ondelete="RESTRICT"))
    version: Mapped[int]
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Top-level definition keys that differ from the previous version (None for version 1).
    changed_fields: Mapped[list[str] | None] = mapped_column(ARRAY(String(50)))
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())
