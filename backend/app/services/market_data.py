"""Import price files into market_data, and query the stored bars."""

from dataclasses import dataclass, field
from datetime import datetime
from itertools import chain
from typing import TextIO

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.errors import InvalidOperationError
from app.market_data import formats
from app.market_data.timeframes import Timeframe
from app.market_data.validation import BarValidator, Rejection, infer_timeframe
from app.schemas.common import Symbol

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


def _normalize_symbol(symbol: str) -> str:
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
    symbol = _normalize_symbol(symbol)
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
