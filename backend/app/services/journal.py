"""The trading journal: entries are drafted, published, then edited only with a reason."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import JournalStatus
from app.errors import ConflictError, InvalidOperationError, NotFoundError
from app.models import JournalEntry, Trade, User
from app.schemas.journal import JournalEntryCreate, JournalEntryUpdate


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
    """Change a draft in place."""
    entry = _get_for_change(db, user, entry_id)
    if entry.status != JournalStatus.DRAFT:
        raise ConflictError(f"Cannot edit a {entry.status} entry")
    changes = data.model_dump(exclude_unset=True)
    _require_own_trade(db, user, changes.get("trade_id"))
    for field, value in changes.items():
        setattr(entry, field, value)
    db.commit()
    db.refresh(entry)
    return entry
