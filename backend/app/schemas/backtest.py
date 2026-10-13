import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.backtest.metrics import Metrics
from app.enums import BacktestStatus
from app.market_data.timeframes import Timeframe
from app.schemas.common import DecimalOut, Price, Symbol

PositionSize = Annotated[Decimal, Field(gt=0, le=100, max_digits=7, decimal_places=4)]
CostPct = Annotated[Decimal, Field(ge=0, le=10, max_digits=7, decimal_places=4)]


class BacktestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: uuid.UUID
    # Defaults to the strategy's current version.
    strategy_version: int | None = Field(default=None, ge=1)
    symbol: Symbol
    timeframe: Timeframe
    # Bar start times, [start, end); an omitted side is open.
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    initial_capital: Price = Decimal(10_000)
    # Share of equity committed to each trade, entry fee included.
    position_size_pct: PositionSize = Decimal(100)
    fee_pct: CostPct = Decimal(0)
    slippage_pct: CostPct = Decimal(0)
    # Annualizes the Sharpe and Sortino ratios: 365 for crypto, 252 for stock exchanges.
    periods_per_year: int = Field(default=365, ge=1, le=366)

    @model_validator(mode="after")
    def _range_is_not_empty(self) -> Self:
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError("start must be before end")
        return self


class BacktestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_version: int
    symbol: str
    timeframe: Timeframe
    start: datetime | None = Field(validation_alias="start_ts")
    end: datetime | None = Field(validation_alias="end_ts")
    initial_capital: DecimalOut
    position_size_pct: DecimalOut
    fee_pct: DecimalOut
    slippage_pct: DecimalOut
    periods_per_year: int
    status: BacktestStatus
    error_message: str | None
    # The bars the run used.
    bars_count: int | None
    first_bar_ts: datetime | None
    last_bar_ts: datetime | None
    data_hash: str | None
    metrics: Metrics | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
