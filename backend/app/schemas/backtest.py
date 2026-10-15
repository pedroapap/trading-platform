import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.backtest.metrics import Metrics, Split
from app.enums import BacktestStatus, Direction, ExitReason
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
    # Finer bars that settle what came first inside a bar where it matters, such as a bar that
    # reaches both the stop-loss and the take-profit: finer than `timeframe`, and dividing it.
    detail_timeframe: Timeframe | None = None
    # Bar start times, [start, end); an omitted side is open.
    start: AwareDatetime | None = None
    end: AwareDatetime | None = None
    # Bars from here on are out-of-sample, reported apart from the bars before.
    out_of_sample_from: AwareDatetime | None = None
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

    @model_validator(mode="after")
    def _split_is_inside_the_range(self) -> Self:
        split = self.out_of_sample_from
        if split is not None and (
            (self.start is not None and split <= self.start)
            or (self.end is not None and split >= self.end)
        ):
            raise ValueError("out_of_sample_from must be between start and end")
        return self

    @model_validator(mode="after")
    def _detail_is_finer(self) -> Self:
        detail = self.detail_timeframe
        if detail is not None and not (
            detail.seconds < self.timeframe.seconds and detail.divides(self.timeframe)
        ):
            raise ValueError("detail_timeframe must be finer than timeframe")
        return self


class BacktestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    strategy_version: int
    symbol: str
    # The currency of the capital, P&L and equity; None until set (see /api/instruments).
    quote_currency: str | None
    timeframe: Timeframe
    detail_timeframe: Timeframe | None
    start: datetime | None = Field(validation_alias="start_ts")
    end: datetime | None = Field(validation_alias="end_ts")
    out_of_sample_from: datetime | None
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
    # With an out-of-sample start, the metrics before it and from it on.
    split_metrics: Split | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class BacktestFilters(BaseModel):
    """Query parameters for listing backtests, newest first."""

    model_config = ConfigDict(extra="forbid")

    strategy_id: uuid.UUID | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class BacktestPage(BaseModel):
    items: list[BacktestRead]
    total: int
    limit: int
    offset: int


class BacktestTradeQuery(BaseModel):
    """Query parameters for a backtest's trades, in the order they were made."""

    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=1000, ge=1, le=10_000)
    offset: int = Field(default=0, ge=0)


class BacktestTradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number: int
    direction: Direction
    entry_time: datetime
    entry_price: DecimalOut
    exit_time: datetime
    exit_price: DecimalOut
    size: DecimalOut
    entry_fee: DecimalOut
    exit_fee: DecimalOut
    slippage: DecimalOut
    pnl: DecimalOut
    pnl_pct: DecimalOut
    exit_reason: ExitReason


class BacktestTradePage(BaseModel):
    items: list[BacktestTradeRead]
    total: int
    limit: int
    offset: int


class EquityPoint(BaseModel):
    ts: datetime
    equity: float
    # Buy and hold's equity at the same time; None for runs made before it was measured.
    benchmark: float | None = None
