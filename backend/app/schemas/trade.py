import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.enums import Direction, TradeStatus
from app.schemas.common import DecimalOut, Fee, Leverage, Price, Symbol


class TradeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: Symbol
    direction: Direction
    entry_price: Price
    entry_time: AwareDatetime
    entry_size: Price
    entry_fee: Fee = Decimal(0)
    stop_loss: Price | None = None
    take_profit: Price | None = None
    leverage: Leverage = Decimal(1)
    strategy_id: uuid.UUID | None = None


# Only these may be cleared with an explicit null; the rest are required on the trade.
CLEARABLE_FIELDS = frozenset({"stop_loss", "take_profit", "strategy_id"})


class TradeUpdate(BaseModel):
    """Corrections to an open trade: omitted fields are unchanged; exits go through /close."""

    model_config = ConfigDict(extra="forbid")

    symbol: Symbol | None = None
    direction: Direction | None = None
    entry_price: Price | None = None
    entry_time: AwareDatetime | None = None
    entry_size: Price | None = None
    entry_fee: Fee | None = None
    stop_loss: Price | None = None
    take_profit: Price | None = None
    leverage: Leverage | None = None
    strategy_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _required_fields_are_not_cleared(self) -> Self:
        for name in self.model_fields_set - CLEARABLE_FIELDS:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True)


class TradeClose(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exit_price: Price
    exit_time: AwareDatetime
    exit_size: Price | None = Field(default=None, description="Defaults to the entry size")
    exit_fee: Fee = Decimal(0)


class TradeCancel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=500)


class TradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID | None
    symbol: str
    direction: Direction
    status: TradeStatus
    entry_price: DecimalOut
    entry_time: datetime
    entry_size: DecimalOut
    entry_fee: DecimalOut
    exit_price: DecimalOut | None
    exit_time: datetime | None
    exit_size: DecimalOut | None
    exit_fee: DecimalOut
    stop_loss: DecimalOut | None
    take_profit: DecimalOut | None
    leverage: DecimalOut
    pnl: DecimalOut | None
    pnl_pct: DecimalOut | None = Field(description="Return on margin (notional / leverage), %")
    created_at: datetime
    updated_at: datetime


class TradeFilters(BaseModel):
    """Query parameters for listing trades; entry times are filtered as [entry_from, entry_to)."""

    model_config = ConfigDict(extra="forbid")

    symbol: Symbol | None = None
    status: TradeStatus | None = None
    strategy_id: uuid.UUID | None = None
    entry_from: AwareDatetime | None = None
    entry_to: AwareDatetime | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
