import uuid
from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, model_validator

from app.enums import EntryType
from app.schemas.common import DecimalOut, Symbol


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


class CurrencyPnl(BaseModel):
    """The P&L of a group's trades quoted in one currency."""

    # None for symbols whose quote currency isn't set; their P&L may mix currencies.
    currency: str | None
    num_trades: int
    total_pnl: DecimalOut
    average_pnl: DecimalOut


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
    # Mean return per trade on its notional, in percent: a trade's return on margin divided
    # by its leverage, as in the backtest comparison.
    average_return_pct: DecimalOut
    # Money per quote currency, never converted: by currency code, an unset currency last.
    by_currency: list[CurrencyPnl]


class PerformanceReport(BaseModel):
    by: GroupBy
    # Best average return first, since totals in different currencies can't be ranked.
    groups: list[PerformanceGroup]


class EquityQuery(BaseModel):
    """Which closed trades make up the realized equity curve; closing times are filtered as
    [closed_from, closed_to)."""

    model_config = ConfigDict(extra="forbid")

    symbol: Symbol | None = None
    strategy_id: uuid.UUID | None = None
    closed_from: AwareDatetime | None = None
    closed_to: AwareDatetime | None = None


class RealizedPoint(BaseModel):
    # When the trade closed.
    ts: datetime
    trade_id: uuid.UUID
    pnl: DecimalOut
    cumulative_pnl: DecimalOut


class RealizedCurve(BaseModel):
    """Realized P&L in one quote currency over time: one point per closed trade, in closing
    order."""

    # None for symbols whose quote currency isn't set; their P&L may mix currencies.
    currency: str | None
    points: list[RealizedPoint]
    total_pnl: DecimalOut
    # The largest fall of the cumulative P&L from an earlier high; the first high is 0.
    max_drawdown: DecimalOut


class RealizedEquity(BaseModel):
    # One curve per quote currency, by code, an unset currency last: P&L in different
    # currencies is never added up.
    curves: list[RealizedCurve]


class ComparisonSide(BaseModel):
    num_trades: int
    win_rate_pct: float | None
    # Mean return per trade on its notional, in percent: a live trade's return on margin is
    # divided by its leverage, so leverage does not skew the comparison.
    average_return_pct: DecimalOut | None
    total_pnl: DecimalOut


class BacktestComparison(BaseModel):
    """A backtest next to the live trades of the same strategy version and symbol entered
    during the bars it covered, [period_start, period_end)."""

    backtest_id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_version: int
    symbol: str
    # The currency of both sides' P&L; None until set (see /api/instruments).
    quote_currency: str | None
    period_start: datetime
    period_end: datetime
    live: ComparisonSide
    backtest: ComparisonSide
