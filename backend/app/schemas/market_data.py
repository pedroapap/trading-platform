from datetime import datetime

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.market_data.timeframes import Timeframe
from app.schemas.common import DecimalOut


class RejectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    line: int
    reason: str


class ImportResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    timeframe: Timeframe
    format: str
    inserted: int
    duplicates: int
    rejected: int
    first_ts: datetime | None
    last_ts: datetime | None
    rejections: list[RejectionRead]


class BarQuery(BaseModel):
    """Bars in [start, end), oldest first; page with start = last bar's ts + one bar."""

    model_config = ConfigDict(extra="forbid")

    timeframe: Timeframe
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    limit: int = Field(default=1000, ge=1, le=10_000)


class BarRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    open: DecimalOut
    high: DecimalOut
    low: DecimalOut
    close: DecimalOut
    volume: DecimalOut


class BarsResponse(BaseModel):
    symbol: str
    timeframe: Timeframe
    bars: list[BarRead]
