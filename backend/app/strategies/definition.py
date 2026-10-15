"""What a strategy does: when to enter, when to leave, and in which direction."""

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.enums import Direction
from app.strategies.rules import Node, Operand, check_limits


def _unset(value: object) -> bool:
    return value is None


# A field the language gained after its first version: left out of a dumped definition while
# unset, so definitions written before it are stored as they were.
def _added(**constraints: object):
    return Field(default=None, exclude_if=_unset, **constraints)


class StrategyDefinition(BaseModel):
    """The versioned part of a strategy: when to enter, in which direction, and how to get out.

    A stop-loss or take-profit is a percentage of the entry price (`_pct`), or a price level
    read on the bar whose signal placed the order (`_at`). A take-profit can also be a
    multiple of the risk, the distance from the entry to the stop-loss (`take_profit_r`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction: Direction
    entry: Node
    exit: Node | None = None
    stop_loss_pct: float | None = Field(default=None, gt=0, le=1000, allow_inf_nan=False)
    take_profit_pct: float | None = Field(default=None, gt=0, le=1000, allow_inf_nan=False)
    stop_loss_at: Operand | None = _added()
    take_profit_at: Operand | None = _added()
    take_profit_r: float | None = _added(gt=0, le=100, allow_inf_nan=False)

    @model_validator(mode="after")
    def _is_tradable(self) -> Self:
        check_limits(self.entry)
        if self.exit is not None:
            check_limits(self.exit)
        stops = [name for name in _STOP_LOSSES if getattr(self, name) is not None]
        targets = [name for name in _TAKE_PROFITS if getattr(self, name) is not None]
        if len(stops) > 1:
            raise ValueError("a strategy has one stop-loss: stop_loss_pct or stop_loss_at")
        if len(targets) > 1:
            raise ValueError(
                "a strategy has one take-profit: take_profit_pct, take_profit_at or take_profit_r"
            )
        if self.take_profit_r is not None and not stops:
            raise ValueError("take_profit_r needs a stop-loss to measure the risk from")
        if self.exit is None and not stops and not targets:
            raise ValueError("a strategy needs an exit rule, a stop-loss or a take-profit")
        # Price cannot fall below zero, so a long's stop or a short's target must be < 100%.
        downside = self.stop_loss_pct if self.direction == Direction.LONG else self.take_profit_pct
        if downside is not None and downside >= 100:
            which = "stop-loss" if self.direction == Direction.LONG else "take-profit"
            raise ValueError(f"a {self.direction} {which} must be below 100%")
        return self


_STOP_LOSSES = ("stop_loss_pct", "stop_loss_at")
_TAKE_PROFITS = ("take_profit_pct", "take_profit_at", "take_profit_r")
