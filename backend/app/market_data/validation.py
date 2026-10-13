"""Check parsed bars before storage, and infer a file's timeframe from its bar spacing."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import pandas as pd

from app.errors import InvalidOperationError
from app.market_data.timeframes import Timeframe

STEP = Decimal("0.00000001")  # the columns keep 8 decimals; Postgres rounds half away from 0
PRICE_LIMIT = Decimal("1e11")  # NUMERIC(19, 8)
VOLUME_LIMIT = Decimal("1e20")  # NUMERIC(28, 8)
PRICES = ("open", "high", "low", "close")

Bar = tuple[datetime, Decimal, Decimal, Decimal, Decimal, Decimal]


@dataclass(frozen=True)
class Rejection:
    line: int
    reason: str


@dataclass
class ValidatedChunk:
    bars: list[Bar] = field(default_factory=list)  # (ts, open, high, low, close, volume)
    rejections: list[Rejection] = field(default_factory=list)


def _decimal(text: object, limit: Decimal) -> Decimal | str:
    """The value rounded to 8 decimals, or a short description of what is wrong."""
    if not isinstance(text, str) or not text.strip():
        return "is missing"
    try:
        value = Decimal(text.strip())
    except InvalidOperation:
        return f"is not a number ({text!r})"
    if not value.is_finite() or abs(value) >= limit:
        return "is out of range"
    return value.quantize(STEP, rounding=ROUND_HALF_UP)


class BarValidator:
    """Validates a file chunk by chunk, remembering timestamps to catch duplicates."""

    def __init__(self, timeframe: Timeframe) -> None:
        self.timeframe = timeframe
        self._step_ns = timeframe.seconds * 1_000_000_000
        self._seen: dict[int, int] = {}  # timestamp (ns) -> line of the accepted bar

    def validate(self, chunk: pd.DataFrame) -> ValidatedChunk:
        result = ValidatedChunk()
        for line, ts, *raw in chunk.itertuples(name=None):
            reasons = []
            values = {}
            for column, text in zip((*PRICES, "volume"), raw, strict=True):
                parsed = _decimal(text, VOLUME_LIMIT if column == "volume" else PRICE_LIMIT)
                if isinstance(parsed, str):
                    reasons.append(f"{column} {parsed}")
                else:
                    values[column] = parsed
            if pd.isna(ts):
                reasons.append("timestamp is missing or unreadable")
            else:
                reasons.extend(self._timing_problems(ts))
            reasons.extend(_price_problems(values))
            if reasons:
                result.rejections.append(Rejection(line, "; ".join(reasons)))
            else:
                # Only accepted bars claim their timestamp; the first valid copy wins.
                self._seen[ts.value] = line
                prices = (values[column] for column in PRICES)
                result.bars.append((ts.to_pydatetime(), *prices, values["volume"]))
        return result

    def _timing_problems(self, ts: pd.Timestamp) -> list[str]:
        problems = []
        if ts.value % self._step_ns:
            problems.append(f"{ts.isoformat()} is not the start of a {self.timeframe} bar")
        if ts.value in self._seen:
            problems.append(f"duplicate of the bar on line {self._seen[ts.value]}")
        return problems


def _price_problems(values: dict[str, Decimal]) -> list[str]:
    problems = [f"{column} must be positive" for column in PRICES if values.get(column, 1) <= 0]
    if values.get("volume", 0) < 0:
        problems.append("volume cannot be negative")
    if all(column in values for column in PRICES):
        body_low = min(values["open"], values["close"])
        body_high = max(values["open"], values["close"])
        if not values["low"] <= body_low <= body_high <= values["high"]:
            problems.append("low/high do not bracket open and close")
    return problems


def infer_timeframe(timestamps: pd.Series) -> Timeframe:
    """The supported timeframe matching the most common spacing between bars."""
    distinct = timestamps.dropna().drop_duplicates().sort_values()
    if len(distinct) < 2:
        raise InvalidOperationError(
            "Need at least two bars to infer the timeframe; pass the timeframe explicitly"
        )
    spacing = distinct.diff().dropna().mode().iloc[0]
    timeframe = Timeframe.from_seconds(int(spacing.total_seconds()))
    if timeframe is None:
        raise InvalidOperationError(
            f"Bars are {spacing} apart, which is not a supported timeframe"
            f" ({', '.join(Timeframe)}); pass the timeframe explicitly"
        )
    return timeframe
