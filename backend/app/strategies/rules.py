"""The strategy rule language: operands compared by conditions, combined with all/any.

Every model is frozen, so identical operands are equal and hashable, which lets the
backtester compute each distinct indicator once.
"""

from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    model_validator,
)

PriceField = Literal["open", "high", "low", "close", "volume"]
Period = Annotated[int, Field(ge=1, le=1000)]
# The value this many bars earlier (1 is the previous bar). Left out of a dumped definition
# when 0, so definitions written before it existed are stored as they were.
BarsAgo = Annotated[int, Field(ge=0, le=1000, exclude_if=lambda bars: bars == 0)]


class _Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Value(_Rule):
    """A constant, e.g. an RSI threshold."""

    value: float = Field(allow_inf_nan=False)


class Price(_Rule):
    """A field of the current bar, or of an earlier one with `bars_ago`."""

    price: PriceField
    bars_ago: BarsAgo = 0


class Sma(_Rule):
    indicator: Literal["sma"]
    period: Period
    source: PriceField = "close"
    bars_ago: BarsAgo = 0


class Ema(_Rule):
    indicator: Literal["ema"]
    period: Period
    source: PriceField = "close"
    bars_ago: BarsAgo = 0


class Rsi(_Rule):
    indicator: Literal["rsi"]
    period: Annotated[int, Field(ge=2, le=1000)] = 14
    source: PriceField = "close"
    bars_ago: BarsAgo = 0


class Macd(_Rule):
    indicator: Literal["macd"]
    fast: Period = 12
    slow: Period = 26
    signal: Period = 9
    output: Literal["line", "signal", "histogram"] = "line"
    source: PriceField = "close"
    bars_ago: BarsAgo = 0

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
    bars_ago: BarsAgo = 0


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


Operator = Literal["<", "<=", ">", ">=", "crosses_above", "crosses_below"]

MAX_DEPTH = 4
MAX_CONDITIONS = 20


class Condition(_Rule):
    """`left op right` on each bar; a cross means it became true on this bar."""

    left: Operand
    op: Operator
    right: Operand

    @model_validator(mode="after")
    def _compares_market_data(self) -> Self:
        if isinstance(self.left, Value) and isinstance(self.right, Value):
            raise ValueError("a condition must involve a price or an indicator")
        return self


def _not_empty(children: tuple) -> tuple:
    # An after-validator rather than min_length, which would also fire when a child is
    # invalid and add a confusing "too short" error next to the real one.
    if not children:
        raise ValueError("a group needs at least one rule")
    return children


class AllOf(_Rule):
    """True when every child is true."""

    all: Annotated[tuple["Node", ...], AfterValidator(_not_empty)]


class AnyOf(_Rule):
    """True when at least one child is true."""

    any: Annotated[tuple["Node", ...], AfterValidator(_not_empty)]


def _node_kind(data: object) -> str | None:
    if isinstance(data, dict):
        return next((key for key in ("all", "any", "op") if key in data), None)
    return {Condition: "op", AllOf: "all", AnyOf: "any"}.get(type(data))


Node = Annotated[
    Annotated[Condition, Tag("op")] | Annotated[AllOf, Tag("all")] | Annotated[AnyOf, Tag("any")],
    Discriminator(
        _node_kind,
        custom_error_type="invalid_rule",
        custom_error_message="A rule is a condition (left/op/right) or an 'all'/'any' group",
    ),
]

AllOf.model_rebuild()
AnyOf.model_rebuild()


def conditions(node: Condition | AllOf | AnyOf) -> list[Condition]:
    """Every condition in the tree, depth first."""
    if isinstance(node, Condition):
        return [node]
    children = node.all if isinstance(node, AllOf) else node.any
    return [condition for child in children for condition in conditions(child)]


def depth(node: Condition | AllOf | AnyOf) -> int:
    if isinstance(node, Condition):
        return 1
    children = node.all if isinstance(node, AllOf) else node.any
    return 1 + max(depth(child) for child in children)


def check_limits(node: Condition | AllOf | AnyOf) -> None:
    """Keep rule trees small enough to read and to evaluate quickly."""
    if depth(node) > MAX_DEPTH:
        raise ValueError(f"rules may be nested at most {MAX_DEPTH} levels deep")
    if len(conditions(node)) > MAX_CONDITIONS:
        raise ValueError(f"rules may contain at most {MAX_CONDITIONS} conditions")
