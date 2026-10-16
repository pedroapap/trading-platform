"""The strategy rule language: operands (values, prices, indicators and arithmetic on them)
compared by conditions, or chart patterns; combined with all/any, negated with not, and
remembered over time with happened.

Every model is frozen, so identical operands are equal and hashable, which lets the
backtester compute each distinct indicator once.
"""

import re
from typing import Annotated, ClassVar, Literal, Self

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

_CLOCK = re.compile(r"^(([01]\d|2[0-3]):[0-5]\d|24:00)$")


def _clock(value: str) -> str:
    if not _CLOCK.match(value):
        raise ValueError("a time of day is HH:MM on a 24-hour clock, such as 09:30")
    return value


# A time of day, "HH:MM"; "24:00" is the end of the day.
ClockTime = Annotated[
    str, AfterValidator(_clock), Field(json_schema_extra={"pattern": _CLOCK.pattern})
]


def minutes(clock: str) -> int:
    """A time of day in minutes after midnight: "09:30" is 570."""
    hours, mins = clock.split(":")
    return int(hours) * 60 + int(mins)


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


class Atr(_Rule):
    """Average true range: how far price moves in a bar, on average (TradingView's `ta.atr`)."""

    indicator: Literal["atr"]
    period: Period = 14
    bars_ago: BarsAgo = 0


class Lowest(_Rule):
    """The lowest `source` of the last `period` bars, this one included (`ta.lowest`)."""

    indicator: Literal["lowest"]
    period: Period
    source: PriceField = "low"
    bars_ago: BarsAgo = 0


class Highest(_Rule):
    """The highest `source` of the last `period` bars, this one included (`ta.highest`)."""

    indicator: Literal["highest"]
    period: Period
    source: PriceField = "high"
    bars_ago: BarsAgo = 0


Strength = Annotated[int, Field(ge=1, le=50)]
Occurrence = Annotated[int, Field(ge=0, le=9)]


class SwingLow(_Rule):
    """A recent swing low: a bar lower than the `strength` bars on each side of it, known only
    `strength` bars after it. `occurrence` 0 is the latest; `output` is its `price` or the
    number of bars since it."""

    indicator: Literal["swing_low"]
    strength: Strength
    occurrence: Occurrence = 0
    output: Literal["price", "bars_since"] = "price"
    source: PriceField = "low"
    bars_ago: BarsAgo = 0


class SwingHigh(_Rule):
    """A recent swing high: a bar higher than the `strength` bars on each side of it (see
    `SwingLow`)."""

    indicator: Literal["swing_high"]
    strength: Strength
    occurrence: Occurrence = 0
    output: Literal["price", "bars_since"] = "price"
    source: PriceField = "high"
    bars_ago: BarsAgo = 0


Indicator = Annotated[
    Sma | Ema | Rsi | Macd | Bbands | Atr | Lowest | Highest | SwingLow | SwingHigh,
    Field(discriminator="indicator"),
]


MAX_ARITHMETIC_DEPTH = 4


def _two(operands: tuple) -> tuple:
    # An after-validator rather than min/max_length, which would also fire when an operand is
    # invalid and add a confusing "too short" error next to the real one.
    if len(operands) != 2:
        raise ValueError("arithmetic takes exactly two operands")
    return operands


# Exactly two operands. A tuple of any length, rather than a pair, so the generated API types
# are plain arrays (as the API client's response types make them) on both sides.
Pair = Annotated[
    tuple["Operand", ...],
    AfterValidator(_two),
    Field(json_schema_extra={"minItems": 2, "maxItems": 2}),
]


class Arithmetic(_Rule):
    """Two operands combined into one value per bar, e.g. `{"multiply": [a, b]}`."""

    key: ClassVar[str]  # the operation, which is also the JSON key

    @property
    def operands(self) -> tuple["Operand", "Operand"]:
        return getattr(self, self.key)

    @model_validator(mode="after")
    def _not_too_deep(self) -> Self:
        if _arithmetic_depth(self) > MAX_ARITHMETIC_DEPTH:
            raise ValueError(f"arithmetic may be nested at most {MAX_ARITHMETIC_DEPTH} levels deep")
        return self


class Add(Arithmetic):
    key: ClassVar[str] = "add"
    add: Pair


class Subtract(Arithmetic):
    """The first operand minus the second."""

    key: ClassVar[str] = "subtract"
    subtract: Pair


class Multiply(Arithmetic):
    key: ClassVar[str] = "multiply"
    multiply: Pair


class Divide(Arithmetic):
    """The first operand divided by the second; unknown where the second is 0."""

    key: ClassVar[str] = "divide"
    divide: Pair


def _arithmetic_depth(operand: "Operand") -> int:
    if isinstance(operand, Arithmetic):
        return 1 + max(_arithmetic_depth(each) for each in operand.operands)
    return 0


_OPERAND_KEYS = ("indicator", "price", "value", "add", "subtract", "multiply", "divide")


def _operand_kind(data: object) -> str | None:
    if isinstance(data, dict):
        return next((key for key in _OPERAND_KEYS if key in data), None)
    if isinstance(data, Value):
        return "value"
    if isinstance(data, Price):
        return "price"
    if isinstance(data, Arithmetic):
        return data.key
    return "indicator" if isinstance(data, _Rule) else None


Operand = Annotated[
    Annotated[Value, Tag("value")]
    | Annotated[Price, Tag("price")]
    | Annotated[Indicator, Tag("indicator")]
    | Annotated[Add, Tag("add")]
    | Annotated[Subtract, Tag("subtract")]
    | Annotated[Multiply, Tag("multiply")]
    | Annotated[Divide, Tag("divide")],
    Discriminator(
        _operand_kind,
        custom_error_type="invalid_operand",
        custom_error_message=(
            "An operand needs a 'value', 'price', 'indicator', 'add', 'subtract', 'multiply'"
            " or 'divide' key"
        ),
    ),
]

for _model in (Add, Subtract, Multiply, Divide):
    _model.model_rebuild()


def is_constant(operand: Operand) -> bool:
    """Whether the operand is the same on every bar: a value, or arithmetic on values."""
    if isinstance(operand, Arithmetic):
        return all(is_constant(each) for each in operand.operands)
    return isinstance(operand, Value)


Operator = Literal["<", "<=", ">", ">=", "crosses_above", "crosses_below"]

MAX_DEPTH = 6
MAX_CONDITIONS = 20


class Condition(_Rule):
    """`left op right` on each bar; a cross means it became true on this bar."""

    left: Operand
    op: Operator
    right: Operand

    @model_validator(mode="after")
    def _compares_market_data(self) -> Self:
        if is_constant(self.left) and is_constant(self.right):
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


class Not(_Rule):
    """True when the rule is false and every value it uses is known, so never while an
    indicator in it is still warming up."""

    # `not` is a Python keyword: the field is `rule`, written `not`.
    model_config = ConfigDict(extra="forbid", frozen=True, serialize_by_alias=True)

    rule: "Node" = Field(alias="not")


class Happened(_Rule):
    """True when the rule held on at least `times` separate runs of bars within the last
    `within` bars, this one included. A run that began before the window counts once if it
    reaches into it."""

    happened: "Node"
    within: Annotated[int, Field(ge=1, le=1000)]
    times: Annotated[int, Field(ge=1, le=10)] = 1


class EqualLows(_Rule):
    """Swing lows at one level, such as a double bottom: true on the bar where the latest of
    `times` swing lows is confirmed. The earlier ones began fewer than `within` bars before it
    and are within `tolerance_pct` of it, and price held that line in between."""

    pattern: Literal["equal_lows"]
    strength: Strength
    times: Annotated[int, Field(ge=2, le=5)] = 2
    within: Annotated[int, Field(ge=2, le=1000)]
    tolerance_pct: float = Field(gt=0, le=10, allow_inf_nan=False)
    source: PriceField = "low"


class EqualHighs(_Rule):
    """Swing highs at one level, such as a double top (see `EqualLows`)."""

    pattern: Literal["equal_highs"]
    strength: Strength
    times: Annotated[int, Field(ge=2, le=5)] = 2
    within: Annotated[int, Field(ge=2, le=1000)]
    tolerance_pct: float = Field(gt=0, le=10, allow_inf_nan=False)
    source: PriceField = "high"


Pattern = Annotated[EqualLows | EqualHighs, Field(discriminator="pattern")]

_NODE_KEYS = ("all", "any", "op", "not", "happened", "pattern")
_NODE_KINDS = {
    Condition: "op",
    AllOf: "all",
    AnyOf: "any",
    Not: "not",
    Happened: "happened",
    EqualLows: "pattern",
    EqualHighs: "pattern",
}


def _node_kind(data: object) -> str | None:
    if isinstance(data, dict):
        return next((key for key in _NODE_KEYS if key in data), None)
    return _NODE_KINDS.get(type(data))


Node = Annotated[
    Annotated[Condition, Tag("op")]
    | Annotated[AllOf, Tag("all")]
    | Annotated[AnyOf, Tag("any")]
    | Annotated[Not, Tag("not")]
    | Annotated[Happened, Tag("happened")]
    | Annotated[Pattern, Tag("pattern")],
    Discriminator(
        _node_kind,
        custom_error_type="invalid_rule",
        custom_error_message=(
            "A rule is a condition (left/op/right), an 'all'/'any' group, 'not', 'happened'"
            " or a 'pattern'"
        ),
    ),
]

for _model in (AllOf, AnyOf, Not, Happened):
    _model.model_rebuild()


def children(node: Node) -> tuple[Node, ...]:
    """The rules directly inside a rule."""
    match node:
        case AllOf(all=rules) | AnyOf(any=rules):
            return rules
        case Not(rule=rule) | Happened(happened=rule):
            return (rule,)
        case _:
            return ()


def leaves(node: Node) -> list[Condition | EqualLows | EqualHighs]:
    """Every condition and pattern in the tree, depth first."""
    inside = children(node)
    if not inside:
        return [node]
    return [leaf for child in inside for leaf in leaves(child)]


def conditions(node: Node) -> list[Condition]:
    """Every condition in the tree, depth first."""
    return [leaf for leaf in leaves(node) if isinstance(leaf, Condition)]


def depth(node: Node) -> int:
    inside = children(node)
    return 1 + max(depth(child) for child in inside) if inside else 1


def check_limits(node: Node) -> None:
    """Keep rule trees small enough to read and to evaluate quickly."""
    if depth(node) > MAX_DEPTH:
        raise ValueError(f"rules may be nested at most {MAX_DEPTH} levels deep")
    if len(leaves(node)) > MAX_CONDITIONS:
        raise ValueError(f"rules may contain at most {MAX_CONDITIONS} conditions and patterns")
