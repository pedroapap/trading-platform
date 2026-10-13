import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.enums import Emotion, EntryType, JournalStatus
from app.errors import ConflictError, InvalidOperationError, NotFoundError
from app.models import JournalEntryVersion
from app.schemas.journal import JournalEntryCreate, JournalEntryUpdate
from app.services import journal, users
from tests.helpers import make_trade


def create(db_session, user, **fields):
    data = {"entry_type": "pre_trade", "title": "BTC range breakout"} | fields
    return journal.create_entry(db_session, user, JournalEntryCreate.model_validate(data))


def update(db_session, user, entry, **fields):
    return journal.update_entry(
        db_session, user, entry.id, JournalEntryUpdate.model_validate(fields)
    )


@pytest.fixture
def other_user(db_session):
    return users.create_user(db_session, "other@example.com", "another-long-password")


def test_an_entry_is_created_as_a_draft(db_session, user):
    trade = make_trade(db_session, user)

    entry = create(
        db_session,
        user,
        trade_id=str(trade.id),
        thesis="Range high breaks on volume",
        emotion="fomo",
        tags=[" Breakout", "FOMO", "breakout"],
    )

    assert (entry.status, entry.current_version, entry.published_at) == (
        JournalStatus.DRAFT,
        0,
        None,
    )
    assert (entry.entry_type, entry.trade_id, entry.emotion) == (
        EntryType.PRE_TRADE,
        trade.id,
        Emotion.FOMO,
    )
    assert entry.tags == ["breakout", "fomo"]  # trimmed, lowercased, without repeats


def test_an_entry_can_only_be_about_the_users_own_trade(db_session, user, other_user):
    trade = make_trade(db_session, other_user)

    for trade_id in (trade.id, uuid.uuid4()):
        with pytest.raises(InvalidOperationError, match="Unknown trade"):
            create(db_session, user, trade_id=str(trade_id))


def test_entries_are_private(db_session, user, other_user):
    entry = create(db_session, user)

    assert journal.get_entry(db_session, user, entry.id) == entry
    with pytest.raises(NotFoundError):
        journal.get_entry(db_session, other_user, entry.id)


def test_a_draft_is_edited_in_place(db_session, user):
    entry = create(db_session, user, thesis="First idea", lessons="None yet")

    edited = update(
        db_session, user, entry, title="BTC breakout, take two", thesis=None, tags=["A"]
    )

    assert (edited.title, edited.thesis, edited.lessons, edited.tags) == (
        "BTC breakout, take two",
        None,
        "None yet",  # omitted, so unchanged
        ["a"],
    )
    assert edited.current_version == 0
    versions = select(JournalEntryVersion).where(JournalEntryVersion.entry_id == entry.id)
    assert db_session.scalars(versions).all() == []


def test_a_draft_cannot_be_linked_to_someone_elses_trade(db_session, user, other_user):
    entry = create(db_session, user)

    with pytest.raises(InvalidOperationError, match="Unknown trade"):
        update(db_session, user, entry, trade_id=str(make_trade(db_session, other_user).id))


@pytest.mark.parametrize(
    "fields",
    [
        {"title": "  "},
        {"title": "x" * 201},
        {"entry_type": "diary"},
        {"emotion": "sleepy"},
        {"tags": ["two words"]},
        {"tags": [""]},
        {"tags": [f"tag{i}" for i in range(21)]},
        {"thesis": "x" * 10_001},
        {"mood": "calm"},
    ],
)
def test_invalid_entries_are_rejected(fields):
    with pytest.raises(ValidationError):
        JournalEntryCreate.model_validate({"entry_type": "note", "title": "Note"} | fields)


@pytest.mark.parametrize("field", ["title", "entry_type", "tags"])
def test_required_fields_cannot_be_cleared(field):
    with pytest.raises(ValidationError, match=f"{field} cannot be null"):
        JournalEntryUpdate.model_validate({field: None})


def test_publishing_freezes_the_content_as_version_one(db_session, user):
    trade = make_trade(db_session, user)
    entry = create(db_session, user, trade_id=str(trade.id), emotion="calm", tags=["plan"])

    published = journal.publish_entry(db_session, user, entry.id)

    assert (published.status, published.current_version) == (JournalStatus.PUBLISHED, 1)
    assert published.published_at is not None
    [version] = db_session.scalars(
        select(JournalEntryVersion).where(JournalEntryVersion.entry_id == entry.id)
    ).all()
    assert (version.version, version.changed_fields, version.edit_reason) == (1, None, None)
    assert version.content == {
        "entry_type": "pre_trade",
        "trade_id": str(trade.id),
        "title": "BTC range breakout",
        "thesis": None,
        "market_context": None,
        "risk_assessment": None,
        "lessons": None,
        "emotion": "calm",
        "tags": ["plan"],
    }


def test_an_entry_is_published_once(db_session, user):
    entry = create(db_session, user)
    journal.publish_entry(db_session, user, entry.id)

    with pytest.raises(ConflictError, match="already published"):
        journal.publish_entry(db_session, user, entry.id)


def test_only_the_author_can_publish(db_session, user, other_user):
    entry = create(db_session, user)

    with pytest.raises(NotFoundError):
        journal.publish_entry(db_session, other_user, entry.id)
