import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.enums import JournalStatus
from app.models import JournalEntryVersion
from tests.helpers import make_journal_entry, make_trade

NOW = datetime(2026, 1, 6, tzinfo=UTC)


def test_an_entry_starts_as_a_draft_without_versions(db_session, user):
    entry = make_journal_entry(db_session, user)

    assert (entry.status, entry.current_version, entry.published_at) == (
        JournalStatus.DRAFT,
        0,
        None,
    )
    assert entry.tags == []


def test_an_entry_can_be_about_a_trade(db_session, user):
    trade = make_trade(db_session, user)

    assert make_journal_entry(db_session, user, trade_id=trade.id).trade_id == trade.id
    with pytest.raises(IntegrityError, match="fk_journal_entries_trade_id_trades"):
        make_journal_entry(db_session, user, trade_id=uuid.uuid4())


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"status": JournalStatus.PUBLISHED, "published_at": NOW}, "versions_when_published"),
        ({"status": JournalStatus.PUBLISHED, "current_version": 1}, "published_at_when_published"),
        ({"current_version": 1}, "versions_when_published"),
        ({"published_at": NOW}, "published_at_when_published"),
    ],
)
def test_only_published_entries_have_versions_and_a_publication_time(
    db_session, user, overrides, constraint
):
    with pytest.raises(IntegrityError, match=f"ck_journal_entries_{constraint}"):
        make_journal_entry(db_session, user, **overrides)


def published_entry(db_session, user):
    entry = make_journal_entry(
        db_session, user, status=JournalStatus.PUBLISHED, current_version=1, published_at=NOW
    )
    db_session.add(JournalEntryVersion(entry_id=entry.id, version=1, content={"title": "v1"}))
    db_session.flush()
    return entry


def test_version_numbers_are_unique_per_entry(db_session, user):
    entry = published_entry(db_session, user)

    db_session.add(JournalEntryVersion(entry_id=entry.id, version=1, content={}))
    with pytest.raises(IntegrityError, match="uq_journal_entry_versions_entry_id"):
        db_session.flush()


@pytest.mark.parametrize(
    ("version", "reason"),
    [(1, "typo fixed"), (2, None)],
    ids=["publication with a reason", "edit without one"],
)
def test_only_edits_after_publishing_have_a_reason(db_session, user, version, reason):
    entry = make_journal_entry(
        db_session, user, status=JournalStatus.PUBLISHED, current_version=1, published_at=NOW
    )

    db_session.add(
        JournalEntryVersion(entry_id=entry.id, version=version, content={}, edit_reason=reason)
    )
    with pytest.raises(IntegrityError, match="ck_journal_entry_versions_edits_have_a_reason"):
        db_session.flush()


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE journal_entry_versions SET content = '{}' WHERE entry_id = :id",
        "DELETE FROM journal_entry_versions WHERE entry_id = :id",
    ],
)
def test_versions_cannot_be_changed(db_session, user, statement):
    entry = published_entry(db_session, user)

    with pytest.raises(IntegrityError, match="journal_entry_versions is append-only"):
        db_session.execute(text(statement), {"id": entry.id})
