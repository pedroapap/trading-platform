"""The strategy rule language: operands compared by conditions, combined with all/any.

Every model is frozen, so identical operands are equal and hashable, which lets the
backtester compute each distinct indicator once.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Discriminator, Field, Tag, model_validator

PriceField = Literal["open", "high", "low", "close", "volume"]
Period = Annotated[int, Field(ge=1, le=1000)]


class _Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Value(_Rule):
    """A constant, e.g. an RSI threshold."""

    value: float = Field(allow_inf_nan=False)


class Price(_Rule):
    """A field of the current bar."""

    price: PriceField


class Sma(_Rule):
    indicator: Literal["sma"]
    period: Period
    source: PriceField = "close"


class Ema(_Rule):
    indicator: Literal["ema"]
    period: Period
    source: PriceField = "close"


class Rsi(_Rule):
    indicator: Literal["rsi"]
    period: Annotated[int, Field(ge=2, le=1000)] = 14
    source: PriceField = "close"


class Macd(_Rule):
    indicator: Literal["macd"]
    fast: Period = 12
    slow: Period = 26
    signal: Period = 9
    output: Literal["line", "signal", "histogram"] = "line"
    source: PriceField = "close"

    @model_validator(mode="after")
    def _fast_is_faster(self) -> Self:
        if self.fast >= self.slow:
            raise ValueError("fast period must be shorter than slow period")
        return self


class Bbands(_Rule):
    indicator: Literal["bbands"]
    period: Annotated[int, Field(ge=2, le=1000)] = 20
    std: float = Field(default=2.0, gt=0, le=10)
    output: Literal["upper", "middle", "lower"] = "middle"
    source: PriceField = "close"


Indicator = Annotated[Sma | Ema | Rsi | Macd | Bbands, Field(discriminator="indicator")]


def _operand_kind(data: object) -> str | None:
    if isinstance(data, dict):
        return next((key for key in ("indicator", "price", "value") if key in data), None)
    if isinstance(data, Value):
        return "value"
    if isinstance(data, Price):
        return "price"
    return "indicator" if isinstance(data, _Rule) else None


Operand = Annotated[
    Annotated[Value, Tag("value")]
    | Annotated[Price, Tag("price")]
    | Annotated[Indicator, Tag("indicator")],
    Discriminator(
        _operand_kind,
        custom_error_type="invalid_operand",
        custom_error_message="An operand needs a 'value', 'price' or 'indicator' key",
    ),
]
