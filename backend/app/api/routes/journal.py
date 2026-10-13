import uuid

from fastapi import APIRouter, status

from app.deps import CurrentUser, DbSession
from app.schemas.journal import JournalEntryCreate, JournalEntryRead, JournalEntryUpdate
from app.services import journal

router = APIRouter(prefix="/journal", tags=["journal"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_entry(body: JournalEntryCreate, db: DbSession, user: CurrentUser) -> JournalEntryRead:
    """Start a draft."""
    return JournalEntryRead.model_validate(journal.create_entry(db, user, body))


@router.get("/{entry_id}")
def get_entry(entry_id: uuid.UUID, db: DbSession, user: CurrentUser) -> JournalEntryRead:
    return JournalEntryRead.model_validate(journal.get_entry(db, user, entry_id))


@router.patch("/{entry_id}")
def update_entry(
    entry_id: uuid.UUID, body: JournalEntryUpdate, db: DbSession, user: CurrentUser
) -> JournalEntryRead:
    """Edit a draft in place, or a published entry with an edit_reason, which keeps the
    previous text as a version."""
    return JournalEntryRead.model_validate(journal.update_entry(db, user, entry_id, body))


@router.post("/{entry_id}/publish")
def publish_entry(entry_id: uuid.UUID, db: DbSession, user: CurrentUser) -> JournalEntryRead:
    """Publish a draft as version 1; from then on, edits need a reason."""
    return JournalEntryRead.model_validate(journal.publish_entry(db, user, entry_id))
