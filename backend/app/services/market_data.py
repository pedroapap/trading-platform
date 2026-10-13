"""Import price files into market_data, and query the stored bars."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from itertools import chain
from typing import Any, TextIO

import pandas as pd
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.errors import InvalidOperationError
from app.market_data import formats
from app.market_data.timeframes import Timeframe
from app.market_data.validation import BarValidator, Rejection, infer_timeframe
from app.models import MarketData
from app.schemas.common import Symbol
from app.schemas.market_data import BarQuery

CHUNK_ROWS = 50_000
MAX_REPORTED_REJECTIONS = 100

_symbol = TypeAdapter(Symbol)


@dataclass
class ImportSummary:
    symbol: str
    timeframe: Timeframe
    format: str
    inserted: int = 0
    duplicates: int = 0
    rejected: int = 0
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    # The first MAX_REPORTED_REJECTIONS problems; `rejected` has the full count.
    rejections: list[Rejection] = field(default_factory=list)


def normalize_symbol(symbol: str) -> str:
    try:
        return _symbol.validate_python(symbol)
    except ValidationError:
        raise InvalidOperationError(f"Invalid symbol {symbol!r}") from None


def _choose_timeframe(requested: Timeframe | None, first_chunk_ts) -> Timeframe:
    if requested is None:
        return infer_timeframe(first_chunk_ts)
    try:
        inferred = infer_timeframe(first_chunk_ts)
    except InvalidOperationError:
        return requested  # too few or irregular bars to second-guess the caller
    if inferred != requested:
        raise InvalidOperationError(
            f"The bars are {inferred} apart, but timeframe {requested} was requested"
        )
    return requested


def import_bars(
    db: Session,
    stream: TextIO,
    symbol: str,
    timeframe: Timeframe | None = None,
    format_name: str | None = None,
    chunk_rows: int = CHUNK_ROWS,
) -> ImportSummary:
    """Validate and store a price file; existing bars are kept and counted as duplicates.

    `stream` must be seekable: the first lines are read to detect the format.
    """
    try:
        return _import(db, stream, symbol, timeframe, format_name, chunk_rows)
    except UnicodeDecodeError:
        raise InvalidOperationError("The file is not UTF-8 text") from None


def _import(
    db: Session,
    stream: TextIO,
    symbol: str,
    timeframe: Timeframe | None,
    format_name: str | None,
    chunk_rows: int,
) -> ImportSummary:
    symbol = normalize_symbol(symbol)
    sample = "".join(stream.readline() for _ in range(formats.SAMPLE_LINES))
    stream.seek(0)
    fmt = formats.get_format(format_name) if format_name else formats.detect(sample)
    chunks = fmt.read(stream, chunk_rows)
    first = next(chunks, None)
    if first is None or first.empty:
        raise InvalidOperationError("The file has no bars")
    summary = ImportSummary(symbol, _choose_timeframe(timeframe, first["ts"]), fmt.name)
    validator = BarValidator(summary.timeframe)

    try:
        db.execute(text("DROP TABLE IF EXISTS import_staging"))
        db.execute(
            text(
                "CREATE TEMP TABLE import_staging (ts timestamptz, open numeric, high numeric,"
                " low numeric, close numeric, volume numeric) ON COMMIT DROP"
            )
        )
        copy_sql = "COPY import_staging (ts, open, high, low, close, volume) FROM STDIN"
        with db.connection().connection.driver_connection.cursor() as cursor:
            for chunk in chain([first], chunks):
                result = validator.validate(chunk)
                summary.rejected += len(result.rejections)
                room = MAX_REPORTED_REJECTIONS - len(summary.rejections)
                summary.rejections.extend(result.rejections[:room])
                with cursor.copy(copy_sql) as copy:
                    for bar in result.bars:
                        copy.write_row(bar)
        staged, summary.first_ts, summary.last_ts = db.execute(
            text("SELECT count(*), min(ts), max(ts) FROM import_staging")
        ).one()
        summary.inserted = db.execute(
            text(
                "INSERT INTO market_data"
                " (symbol, timeframe, ts, open, high, low, close, volume, source)"
                " SELECT :symbol, :timeframe, ts, open, high, low, close, volume, :source"
                " FROM import_staging ON CONFLICT DO NOTHING"
            ),
            {"symbol": symbol, "timeframe": summary.timeframe.value, "source": fmt.name},
        ).rowcount
        summary.duplicates = staged - summary.inserted
        db.commit()
    except Exception:
        db.rollback()
        raise
    return summary


@dataclass(frozen=True)
class Bars:
    bars: Sequence[Any]  # rows with ts, open, high, low, close and volume
    aggregated_from: Timeframe | None  # None when the bars are stored at this timeframe


def _range_filter(start: datetime | None, end: datetime | None) -> str:
    return (" AND ts >= :start" if start else "") + (" AND ts < :end" if end else "")


def _stored_timeframes(
    db: Session, symbol: str, start: datetime | None, end: datetime | None
) -> set[Timeframe]:
    """Timeframes with at least one bar in the range (one index probe per timeframe)."""
    statement = text(
        "SELECT tf FROM unnest(CAST(:timeframes AS text[])) AS tf WHERE EXISTS ("
        " SELECT 1 FROM market_data WHERE symbol = :symbol AND timeframe = tf"
        f"{_range_filter(start, end)})"
    )
    params = {"timeframes": list(Timeframe), "symbol": symbol, "start": start, "end": end}
    return {Timeframe(tf) for tf in db.scalars(statement, params)}


BAR_FIELDS = ("open", "high", "low", "close", "volume")

# Each field of a bar built from finer bars, aggregated over its time bucket.
_AGGREGATED = {
    "open": "first(open, ts)",
    "high": "max(high)",
    "low": "min(low)",
    "close": "last(close, ts)",
    "volume": "sum(volume)",
}


def _whole_bars(
    timeframe: Timeframe, start: datetime | None, end: datetime | None
) -> tuple[datetime | None, datetime | None]:
    """The range widened to whole bars, so no bar is built from a partial bucket at the start."""
    return (timeframe.ceil(start) if start else None, timeframe.ceil(end) if end else None)


def _source_timeframe(
    db: Session, symbol: str, timeframe: Timeframe, start: datetime | None, end: datetime | None
) -> Timeframe | None:
    """The coarsest stored timeframe with bars in the range that `timeframe` bars can be
    built from (itself included); None when the range holds no bars of the symbol."""
    stored = _stored_timeframes(db, symbol, start, end)
    sources = [tf for tf in stored if tf.divides(timeframe)]
    if stored and not sources:
        available = ", ".join(sorted(stored, key=lambda tf: tf.seconds))
        raise InvalidOperationError(
            f"{symbol} has no {timeframe} bars, or finer bars to build them from,"
            f" in this range (stored: {available})"
        )
    return max(sources, key=lambda tf: tf.seconds, default=None)


def _bars_statement(
    timeframe: Timeframe,
    source: Timeframe,
    start: datetime | None,
    end: datetime | None,
    value_type: str | None = None,
) -> str:
    """SQL for the :symbol's `timeframe` bars in the range, built from `source` bars, oldest
    first; values are cast to `value_type` if given."""
    aggregated = source != timeframe
    expressions = _AGGREGATED if aggregated else {field: field for field in BAR_FIELDS}
    if value_type:
        expressions = {field: f"CAST({sql} AS {value_type})" for field, sql in expressions.items()}
    columns = ", ".join(f"{sql} AS {field}" for field, sql in expressions.items())
    ts = "time_bucket(CAST(:width AS interval), ts)" if aggregated else "ts"
    return (
        f"SELECT {ts} AS ts, {columns} FROM market_data"
        f" WHERE symbol = :symbol AND timeframe = :source{_range_filter(start, end)}"
        f"{' GROUP BY 1' if aggregated else ''} ORDER BY 1"
    )


def get_bars(db: Session, symbol: str, query: BarQuery) -> Bars:
    """Bars at `query.timeframe`: stored ones, or built from the coarsest stored timeframe
    that divides it."""
    symbol = normalize_symbol(symbol)
    start, end = _whole_bars(query.timeframe, query.start, query.end)
    source = _source_timeframe(db, symbol, query.timeframe, start, end)
    if source is None:
        return Bars([], None)
    statement = _bars_statement(query.timeframe, source, start, end) + " LIMIT :limit"
    params = {"symbol": symbol, "source": source.value, "start": start, "end": end}
    params |= {"width": query.timeframe.delta, "limit": query.limit}
    rows = db.execute(text(statement), params).all()
    return Bars(rows, None if source == query.timeframe else source)


def load_bars(
    db: Session,
    symbol: str,
    timeframe: Timeframe,
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame:
    """Every bar for a backtest, as `get_bars` builds them but without a row limit: float
    columns indexed by bar start time (UTC)."""
    symbol = normalize_symbol(symbol)
    start, end = _whole_bars(timeframe, start, end)
    source = _source_timeframe(db, symbol, timeframe, start, end)
    if source is None:
        raise InvalidOperationError(f"There are no {symbol} bars in this range")
    statement = _bars_statement(timeframe, source, start, end, value_type="float8")
    params = {"symbol": symbol, "source": source.value, "start": start, "end": end}
    rows = db.execute(text(statement), params | {"width": timeframe.delta}).all()
    bars = pd.DataFrame(rows, columns=["ts", *BAR_FIELDS])
    return bars.set_index(pd.DatetimeIndex(pd.to_datetime(bars.pop("ts"), utc=True), name="ts"))


@dataclass(frozen=True)
class Coverage:
    symbol: str
    timeframe: Timeframe
    first_ts: datetime
    last_ts: datetime
    bars: int


def coverage(db: Session) -> list[Coverage]:
    """Stored bars per symbol and timeframe, ordered by symbol then bar size."""
    rows = db.execute(
        select(
            MarketData.symbol,
            MarketData.timeframe,
            func.min(MarketData.ts),
            func.max(MarketData.ts),
            func.count(),
        ).group_by(MarketData.symbol, MarketData.timeframe)
    )
    found = [Coverage(*row) for row in rows]
    return sorted(found, key=lambda c: (c.symbol, c.timeframe.seconds))
