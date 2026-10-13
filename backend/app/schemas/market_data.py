from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.market_data.timeframes import Timeframe


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
