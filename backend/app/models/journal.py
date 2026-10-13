import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.enums import Emotion, EntryType, JournalStatus
from app.models.base import Base, TimestampMixin, enum_check, str_enum


class JournalEntry(TimestampMixin, Base):
    """A journal entry, optionally about one trade. A draft changes in place; once published,
    each edit is kept as a new version."""

    __tablename__ = "journal_entries"
    __table_args__ = (
        enum_check("entry_type", EntryType),
        enum_check("emotion", Emotion),
        enum_check("status", JournalStatus),
        CheckConstraint("current_version >= 0", name="version_not_negative"),
        CheckConstraint(
            "(status = 'published') = (current_version >= 1)", name="versions_when_published"
        ),
        CheckConstraint(
            "(status = 'published') = (published_at IS NOT NULL)",
            name="published_at_when_published",
        ),
        Index("ix_journal_entries_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    trade_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("trades.id", ondelete="RESTRICT"))

    entry_type: Mapped[EntryType] = mapped_column(str_enum(EntryType, "entry_type"))
    title: Mapped[str] = mapped_column(String(200))
    thesis: Mapped[str | None] = mapped_column(Text)
    market_context: Mapped[str | None] = mapped_column(Text)
    risk_assessment: Mapped[str | None] = mapped_column(Text)
    lessons: Mapped[str | None] = mapped_column(Text)
    emotion: Mapped[Emotion | None] = mapped_column(str_enum(Emotion, "emotion"))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(50)), server_default=text("'{}'"))

    status: Mapped[JournalStatus] = mapped_column(
        str_enum(JournalStatus, "status"), server_default=JournalStatus.DRAFT.value
    )
    # 0 for a draft; the latest version once published.
    current_version: Mapped[int] = mapped_column(server_default=text("0"))
    published_at: Mapped[datetime | None]
    # The insert's own time, not its transaction's, so creation order is exact.
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())


class JournalEntryVersion(Base):
    """A published state of an entry: version 1 is the publication, later ones are edits.
    A database trigger rejects UPDATE/DELETE, so the history cannot be rewritten."""

    __tablename__ = "journal_entry_versions"
    __table_args__ = (
        UniqueConstraint("entry_id", "version"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("(version = 1) = (edit_reason IS NULL)", name="edits_have_a_reason"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.gen_random_uuid())
    entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("journal_entries.id", ondelete="RESTRICT")
    )
    version: Mapped[int]
    content: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Content fields that differ from the previous version (None for version 1).
    changed_fields: Mapped[list[str] | None] = mapped_column(ARRAY(String(50)))
    # Why the published entry was edited (None for version 1, the publication).
    edit_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=func.clock_timestamp())
