import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from app.enums import Emotion, EntryType, JournalStatus

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
LongText = Annotated[str, Field(max_length=10_000)]


def _normalize_tag(value: object) -> object:
    return value.strip().lower() if isinstance(value, str) else value


# Normalized before validating, since StringConstraints checks the pattern first.
Tag = Annotated[
    str,
    BeforeValidator(_normalize_tag),
    StringConstraints(min_length=1, max_length=50, pattern=r"^[a-z0-9][a-z0-9_-]*$"),
]


def _without_duplicates(tags: list[str]) -> list[str]:
    return list(dict.fromkeys(tags))


Tags = Annotated[list[Tag], Field(max_length=20), AfterValidator(_without_duplicates)]


class JournalContent(BaseModel):
    """What an entry says. Each published version keeps a snapshot of it."""

    entry_type: EntryType
    # One of the user's own trades.
    trade_id: uuid.UUID | None = None
    title: Title
    thesis: LongText | None = None
    market_context: LongText | None = None
    risk_assessment: LongText | None = None
    lessons: LongText | None = None
    emotion: Emotion | None = None
    tags: Tags = []


class JournalEntryCreate(JournalContent):
    model_config = ConfigDict(extra="forbid")


class JournalEntryUpdate(BaseModel):
    """Omitted fields are unchanged; null clears an optional one. Editing a published entry
    needs an edit_reason; a draft takes none."""

    model_config = ConfigDict(extra="forbid")

    entry_type: EntryType | None = None
    trade_id: uuid.UUID | None = None
    title: Title | None = None
    thesis: LongText | None = None
    market_context: LongText | None = None
    risk_assessment: LongText | None = None
    lessons: LongText | None = None
    emotion: Emotion | None = None
    tags: Tags | None = None
    edit_reason: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
        | None
    ) = None

    @model_validator(mode="after")
    def _required_fields_are_not_cleared(self) -> Self:
        for name in ("entry_type", "title", "tags"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class JournalEntryRead(JournalContent):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: JournalStatus
    # 0 for a draft; the latest version once published.
    current_version: int
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class JournalFilters(BaseModel):
    """Query parameters for listing entries, newest first; creation times are filtered as
    [created_from, created_to)."""

    model_config = ConfigDict(extra="forbid")

    entry_type: EntryType | None = None
    trade_id: uuid.UUID | None = None
    status: JournalStatus | None = None
    emotion: Emotion | None = None
    tag: Tag | None = None
    created_from: AwareDatetime | None = None
    created_to: AwareDatetime | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class JournalPage(BaseModel):
    items: list[JournalEntryRead]
    total: int
    limit: int
    offset: int
