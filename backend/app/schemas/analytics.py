from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from app.enums import EntryType
from app.schemas.common import DecimalOut


class GroupBy(StrEnum):
    STRATEGY = "strategy"
    SYMBOL = "symbol"
    # Emotions and tags come from the journal entries about each trade.
    EMOTION = "emotion"
    TAG = "tag"


class PerformanceQuery(BaseModel):
    """Closed trades grouped by one of their attributes; closing times are filtered as
    [closed_from, closed_to)."""

    model_config = ConfigDict(extra="forbid")

    by: GroupBy
    closed_from: AwareDatetime | None = None
    closed_to: AwareDatetime | None = None
    # For emotions and tags: only use journal entries of this type, e.g. pre-trade feelings.
    entry_type: EntryType | None = None

    @model_validator(mode="after")
    def _entry_type_only_for_journal_groupings(self) -> Self:
        if self.entry_type is not None and self.by not in (GroupBy.EMOTION, GroupBy.TAG):
            raise ValueError("entry_type only applies when grouping by emotion or tag")
        return self


class PerformanceGroup(BaseModel):
    # The strategy id, symbol, emotion or tag; None for trades without one.
    key: str | None
    # What to show for the key: the strategy's name, or the key itself.
    label: str | None
    num_trades: int
    # P&L above zero; breakeven trades are neither wins nor losses.
    wins: int
    losses: int
    win_rate_pct: float
    total_pnl: DecimalOut
    average_pnl: DecimalOut


class PerformanceReport(BaseModel):
    by: GroupBy
    # Best total P&L first.
    groups: list[PerformanceGroup]
