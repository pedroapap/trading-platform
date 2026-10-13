from decimal import Decimal

import pandas as pd
import pytest

from app.errors import InvalidOperationError
from app.market_data.timeframes import Timeframe
from app.market_data.validation import BarValidator, Rejection, infer_timeframe

COLUMNS = ["ts", "open", "high", "low", "close", "volume"]
GOOD = ["2026-01-05T00:00Z", "100", "105", "99", "104", "0.00012345"]


def chunk(*rows: list[str], first_line: int = 2) -> pd.DataFrame:
    frame = pd.DataFrame([list(row) for row in rows], columns=COLUMNS)
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="coerce", format="ISO8601")
    frame.index = pd.RangeIndex(first_line, first_line + len(frame))
    return frame


def test_valid_bars_become_exact_decimals():
    result = BarValidator(Timeframe.M1).validate(chunk(GOOD))

    assert result.rejections == []
    ((ts, *values),) = result.bars
    assert ts == pd.Timestamp("2026-01-05", tz="UTC").to_pydatetime()
    assert values == [
        Decimal("100"),
        Decimal("105"),
        Decimal("99"),
        Decimal("104"),
        Decimal("0.00012345"),
    ]


def test_values_are_rounded_to_eight_decimals():
    row = ["2026-01-05T00:00Z", "1.123456785", "2", "1", "1.5", "3"]

    ((_, open_, *_),) = BarValidator(Timeframe.M1).validate(chunk(row)).bars

    assert open_ == Decimal("1.12345679")


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        (["nonsense", "100", "105", "99", "104", "1"], "timestamp is missing or unreadable"),
        (["2026-01-05T00:00Z", "abc", "105", "99", "104", "1"], "open is not a number ('abc')"),
        (["2026-01-05T00:00Z", "100", "", "99", "104", "1"], "high is missing"),
        (["2026-01-05T00:00Z", "1e12", "1e12", "99", "104", "1"], "open is out of range"),
        (["2026-01-05T00:00Z", "0", "105", "0", "104", "1"], "open must be positive"),
        (["2026-01-05T00:00Z", "100", "105", "99", "104", "-1"], "volume cannot be negative"),
        (["2026-01-05T00:00Z", "100", "103", "99", "104", "1"], "low/high do not bracket"),
        (["2026-01-05T00:00:30Z", "100", "105", "99", "104", "1"], "is not the start of a 1m bar"),
    ],
)
def test_invalid_rows_are_rejected_with_their_line_and_reason(row, reason):
    result = BarValidator(Timeframe.M1).validate(chunk(GOOD, row))

    assert len(result.bars) == 1
    (rejection,) = result.rejections
    assert rejection.line == 3
    assert reason in rejection.reason


def test_all_problems_of_a_row_are_reported_together():
    row = ["2026-01-05T00:00:30Z", "-1", "105", "99", "104", "-5"]

    (rejection,) = BarValidator(Timeframe.M1).validate(chunk(row)).rejections

    assert rejection.reason.count(";") == 3


def test_duplicates_are_caught_across_chunks():
    validator = BarValidator(Timeframe.M1)
    validator.validate(chunk(GOOD))

    second = validator.validate(chunk(GOOD, first_line=1002))

    assert second.rejections == [Rejection(1002, "duplicate of the bar on line 2")]


def test_a_rejected_row_does_not_block_a_later_valid_copy():
    broken = [GOOD[0], "abc", *GOOD[2:]]

    result = BarValidator(Timeframe.M1).validate(chunk(broken, GOOD))

    assert [r.line for r in result.rejections] == [2]
    assert len(result.bars) == 1


def series(*timestamps: str) -> pd.Series:
    return pd.Series(pd.to_datetime(list(timestamps), utc=True))


def test_infers_minutes_despite_gaps():
    ts = series("2026-01-05 00:00", "2026-01-05 00:01", "2026-01-05 00:02", "2026-01-05 00:05")

    assert infer_timeframe(ts) is Timeframe.M1


def test_infers_daily_bars_across_weekends():
    days = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]

    assert infer_timeframe(series(*days)) is Timeframe.D1


@pytest.mark.parametrize(
    ("timestamps", "message"),
    [
        (["2026-01-05 00:00"], "Need at least two bars"),
        (["2026-01-05 00:00", "2026-01-05 00:02", "2026-01-05 00:04"], "not a supported timeframe"),
    ],
)
def test_inference_failures_ask_for_an_explicit_timeframe(timestamps, message):
    with pytest.raises(InvalidOperationError, match=message):
        infer_timeframe(series(*timestamps))
