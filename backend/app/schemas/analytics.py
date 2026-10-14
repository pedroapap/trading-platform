from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.schemas.common import DecimalOut


class GroupBy(StrEnum):
    STRATEGY = "strategy"
    SYMBOL = "symbol"


class PerformanceQuery(BaseModel):
    """Closed trades grouped by one of their attributes; closing times are filtered as
    [closed_from, closed_to)."""

    model_config = ConfigDict(extra="forbid")

    by: GroupBy
    closed_from: AwareDatetime | None = None
    closed_to: AwareDatetime | None = None


class PerformanceGroup(BaseModel):
    # The strategy id or symbol; None for trades without one.
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
