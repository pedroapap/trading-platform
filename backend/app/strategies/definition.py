"""What a strategy does: when to enter, when to leave, and in which direction."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.enums import Direction
from app.strategies.rules import Node, check_limits


class StrategyDefinition(BaseModel):
    """The versioned part of a strategy. Stop-loss and take-profit are percentages of the
    entry price."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction: Direction
    entry: Node
    exit: Node | None = None
    stop_loss_pct: float | None = Field(default=None, gt=0, le=1000, allow_inf_nan=False)
    take_profit_pct: float | None = Field(default=None, gt=0, le=1000, allow_inf_nan=False)

    @model_validator(mode="after")
    def _is_tradable(self) -> Self:
        check_limits(self.entry)
        if self.exit is not None:
            check_limits(self.exit)
        if self.exit is None and self.stop_loss_pct is None and self.take_profit_pct is None:
            raise ValueError("a strategy needs an exit rule, a stop-loss or a take-profit")
        # Price cannot fall below zero, so a long's stop or a short's target must be < 100%.
        downside = self.stop_loss_pct if self.direction == Direction.LONG else self.take_profit_pct
        if downside is not None and downside >= 100:
            which = "stop-loss" if self.direction == Direction.LONG else "take-profit"
            raise ValueError(f"a {self.direction} {which} must be below 100%")
        return self
