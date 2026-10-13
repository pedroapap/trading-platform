"""The trading journal: entries are drafted, published, then edited only with a reason."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import JournalStatus
from app.errors import ConflictError, InvalidOperationError, NotFoundError
from app.models import JournalEntry, JournalEntryVersion, Trade, User
from app.schemas.journal import (
    JournalContent,
    JournalEntryCreate,
    JournalEntryUpdate,
    JournalFilters,
)


def _require_own_trade(db: Session, user: User, trade_id: uuid.UUID | None) -> None:
    """The foreign key only proves the trade exists; it must also be the user's own."""
    if trade_id is None:
        return
    owned = select(Trade.id).where(Trade.id == trade_id, Trade.user_id == user.id)
    if db.scalar(owned) is None:
        raise InvalidOperationError("Unknown trade")


def create_entry(db: Session, user: User, data: JournalEntryCreate) -> JournalEntry:
    """A draft entry."""
    _require_own_trade(db, user, data.trade_id)
    entry = JournalEntry(user_id=user.id, **data.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_entry(db: Session, user: User, entry_id: uuid.UUID) -> JournalEntry:
    query = select(JournalEntry).where(JournalEntry.id == entry_id, JournalEntry.user_id == user.id)
    entry = db.scalar(query)
    if entry is None:
        raise NotFoundError("Journal entry not found")
    return entry


def list_entries(
    db: Session, user: User, filters: JournalFilters
) -> tuple[list[JournalEntry], int]:
    """Matching entries, newest first, plus the total count before pagination."""
    query = select(JournalEntry).where(JournalEntry.user_id == user.id)
    for field in ("entry_type", "trade_id", "status", "emotion"):
        if (value := getattr(filters, field)) is not None:
            query = query.where(getattr(JournalEntry, field) == value)
    if filters.tag is not None:
        query = query.where(JournalEntry.tags.contains([filters.tag]))
    if filters.created_from is not None:
        query = query.where(JournalEntry.created_at >= filters.created_from)
    if filters.created_to is not None:
        query = query.where(JournalEntry.created_at < filters.created_to)

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    page = query.order_by(JournalEntry.created_at.desc()).limit(filters.limit)
    return list(db.scalars(page.offset(filters.offset))), total or 0


def _get_for_change(db: Session, user: User, entry_id: uuid.UUID) -> JournalEntry:
    """Load and row-lock the entry so concurrent changes are applied one at a time."""
    query = select(JournalEntry).where(JournalEntry.id == entry_id, JournalEntry.user_id == user.id)
    entry = db.scalar(query.with_for_update())
    if entry is None:
        raise NotFoundError("Journal entry not found")
    return entry


def update_entry(
    db: Session, user: User, entry_id: uuid.UUID, data: JournalEntryUpdate
) -> JournalEntry:
    """Change a draft in place. A published entry needs an edit_reason, and an edit that
    changes something becomes its next version, recording which fields changed."""
    entry = _get_for_change(db, user, entry_id)
    published = entry.status == JournalStatus.PUBLISHED
    if published and data.edit_reason is None:
        raise InvalidOperationError("Editing a published entry needs an edit_reason")
    if not published and data.edit_reason is not None:
        raise InvalidOperationError("A draft is edited without an edit_reason")
    changes = data.model_dump(exclude_unset=True, exclude={"edit_reason"})
    _require_own_trade(db, user, changes.get("trade_id"))

    if published:
        before = _content(entry)
        after = JournalContent.model_validate(before | changes).model_dump(mode="json")
        changed = sorted(field for field in after if after[field] != before[field])
        if not changed:
            db.commit()  # nothing to record; releases the row lock
            return entry
        entry.current_version += 1
        db.add(
            JournalEntryVersion(
                entry_id=entry.id,
                version=entry.current_version,
                content=after,
                changed_fields=changed,
                edit_reason=data.edit_reason,
            )
        )
    for field, value in changes.items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return entry


def publish_entry(db: Session, user: User, entry_id: uuid.UUID) -> JournalEntry:
    """Publish a draft: its content becomes version 1, which later edits build on."""
    entry = _get_for_change(db, user, entry_id)
    if entry.status != JournalStatus.DRAFT:
        raise ConflictError("The entry is already published")
    entry.status = JournalStatus.PUBLISHED
    entry.current_version = 1
    entry.published_at = func.clock_timestamp()
    db.add(JournalEntryVersion(entry_id=entry.id, version=1, content=_content(entry)))
    db.commit()
    db.refresh(entry)
    return entry


def _content(entry: JournalEntry) -> dict[str, Any]:
    """The entry's content as a JSON snapshot."""
    return JournalContent.model_validate(entry, from_attributes=True).model_dump(mode="json")
