"""What a strategy does: when to enter, when to leave, and in which direction."""

from functools import cache
from typing import Annotated, Literal, Self
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.enums import Direction
from app.strategies.rules import ClockTime, Node, Operand, check_limits, minutes


def _unset(value: object) -> bool:
    return value is None


# A field the language gained after its first version: left out of a dumped definition while
# unset, so definitions written before it are stored as they were.
def _added(**constraints: object):
    return Field(default=None, exclude_if=_unset, **constraints)


@cache
def _time_zones() -> frozenset[str]:
    return frozenset(available_timezones())


class Session(BaseModel):
    """When the market trades each day, in its own time zone: an IANA name such as
    America/New_York, whose daylight saving is followed. A bar belongs to the trading day whose
    session it overlaps; a bar that overlaps none is outside the session. Without a session,
    the trading day is the whole UTC day."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    timezone: str = "UTC"
    start: ClockTime = "00:00"
    end: ClockTime = "24:00"

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, zone: str) -> str:
        if zone not in _time_zones():
            raise ValueError(
                f"unknown time zone {zone!r}: use an IANA name, such as America/New_York"
            )
        return zone

    @model_validator(mode="after")
    def _within_a_day(self) -> Self:
        if minutes(self.start) >= minutes(self.end):
            raise ValueError("a session starts before it ends, on the same day")
        return self


class MarketEntry(BaseModel):
    """Enter at the next bar's open."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["market"]


class PriceEntry(BaseModel):
    """Enter with an order at `price`, read on the signal bar: a `limit` order fills at that
    price or better (a long buys at or below it); a `stop` order fills once price trades
    through it (a long buys at or above it). It works for `expires_after` bars from the next
    one, unless a newer signal replaces it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["limit", "stop"]
    price: Operand
    expires_after: int = Field(default=1, ge=1, le=1000)


EntryOrder = Annotated[MarketEntry | PriceEntry, Field(discriminator="type")]


class StrategyDefinition(BaseModel):
    """The versioned part of a strategy: when to enter, in which direction, and how to get out.

    A stop-loss or take-profit is a percentage of the entry price (`_pct`), or a price level
    read on the bar whose signal placed the order (`_at`). A take-profit can also be a
    multiple of the risk, the distance from the entry to the stop-loss (`take_profit_r`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direction: Direction
    entry: Node
    exit: Node | None = None
    # When the trading day runs; the UTC day when left out.
    session: Session | None = _added()
    stop_loss_pct: float | None = Field(default=None, gt=0, le=1000, allow_inf_nan=False)
    take_profit_pct: float | None = Field(default=None, gt=0, le=1000, allow_inf_nan=False)
    stop_loss_at: Operand | None = _added()
    take_profit_at: Operand | None = _added()
    take_profit_r: float | None = _added(gt=0, le=100, allow_inf_nan=False)
    # How entry signals enter; at the next open when left out.
    entry_order: EntryOrder | None = _added()
    # A stop that follows the trade and only tightens: a percentage behind the best price since
    # the entry, or a price level read on each close and used from the next bar.
    trailing_stop_pct: float | None = _added(gt=0, le=1000, allow_inf_nan=False)
    trailing_stop_at: Operand | None = _added()
    # Leave at the open this many bars after the entry bar, unless something exits first.
    exit_after_bars: int | None = _added(ge=1, le=100_000)

    @model_validator(mode="after")
    def _is_tradable(self) -> Self:
        check_limits(self.entry)
        if self.exit is not None:
            check_limits(self.exit)
        stops = [name for name in _STOP_LOSSES if getattr(self, name) is not None]
        targets = [name for name in _TAKE_PROFITS if getattr(self, name) is not None]
        trailing = [name for name in _TRAILING_STOPS if getattr(self, name) is not None]
        if len(stops) > 1:
            raise ValueError("a strategy has one stop-loss: stop_loss_pct or stop_loss_at")
        if len(trailing) > 1:
            raise ValueError(
                "a strategy has one trailing stop: trailing_stop_pct or trailing_stop_at"
            )
        if len(targets) > 1:
            raise ValueError(
                "a strategy has one take-profit: take_profit_pct, take_profit_at or take_profit_r"
            )
        if self.take_profit_r is not None and not stops:
            raise ValueError("take_profit_r needs a stop-loss to measure the risk from")
        if self.exit is None and not (stops or targets or trailing or self.exit_after_bars):
            raise ValueError(
                "a strategy needs a way out: an exit rule, a stop-loss, a take-profit, a trailing"
                " stop or exit_after_bars"
            )
        # Price cannot fall below zero, so a long's stops or a short's target must be < 100%.
        downside = (
            {"stop-loss": self.stop_loss_pct, "trailing stop": self.trailing_stop_pct}
            if self.direction == Direction.LONG
            else {"take-profit": self.take_profit_pct}
        )
        for which, pct in downside.items():
            if pct is not None and pct >= 100:
                raise ValueError(f"a {self.direction} {which} must be below 100%")
        return self


_STOP_LOSSES = ("stop_loss_pct", "stop_loss_at")
_TAKE_PROFITS = ("take_profit_pct", "take_profit_at", "take_profit_r")
_TRAILING_STOPS = ("trailing_stop_pct", "trailing_stop_at")
