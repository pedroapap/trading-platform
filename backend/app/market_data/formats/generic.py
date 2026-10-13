"""CSV with a header row: Yahoo Finance and TradingView exports, and most vendors' layouts."""

import csv
from collections.abc import Iterator
from typing import TextIO

import pandas as pd

from app.errors import InvalidOperationError
from app.market_data.formats.base import BAR_COLUMNS, parse_timestamps

# Accepted header names per bar column (compared lowercase, spaces as underscores).
ALIASES = {
    "ts": ("time", "timestamp", "date", "datetime", "date_time", "open_time"),
    "open": ("open", "o"),
    "high": ("high", "h"),
    "low": ("low", "l"),
    "close": ("close", "c"),
    "volume": ("volume", "vol", "v"),
}
REQUIRED = ("ts", "open", "high", "low", "close")


def _delimiter(header: str) -> str:
    return max((",", ";", "\t"), key=header.count)


def _column_positions(names: list[str]) -> dict[str, int] | None:
    """Position of each bar column in the header, or None if a required one is missing."""
    normalized = [name.strip().lower().replace(" ", "_") for name in names]
    positions = {}
    for column, aliases in ALIASES.items():
        found = next((normalized.index(a) for a in aliases if a in normalized), None)
        if found is not None:
            positions[column] = found
    return positions if all(column in positions for column in REQUIRED) else None


def _header(line: str) -> tuple[str, list[str]]:
    delimiter = _delimiter(line)
    return delimiter, next(csv.reader([line], delimiter=delimiter))


class GenericOhlcvFormat:
    name = "generic_ohlcv"
    description = (
        "CSV with a header row: a time/date column plus open, high, low, close and optional"
        " volume (Yahoo Finance, TradingView exports, ...)"
    )

    def sniff(self, sample: str) -> bool:
        first_line = sample.lstrip().partition("\n")[0]
        return _column_positions(_header(first_line)[1]) is not None

    def read(self, stream: TextIO, chunk_rows: int) -> Iterator[pd.DataFrame]:
        delimiter, names = _header(stream.readline())
        positions = _column_positions(names)
        if positions is None:
            raise InvalidOperationError(
                "The header needs a time/date column and open, high, low and close columns"
            )
        chunks = pd.read_csv(
            stream,
            sep=delimiter,
            header=None,
            names=range(len(names)),
            dtype=str,
            keep_default_na=False,
            skipinitialspace=True,
            chunksize=chunk_rows,
        )
        next_line = 2  # line 1 is the header
        try:
            for chunk in chunks:
                frame = pd.DataFrame({column: chunk[pos] for column, pos in positions.items()})
                if "volume" not in frame:
                    frame["volume"] = "0"
                frame["ts"] = parse_timestamps(frame["ts"])
                frame.index = pd.RangeIndex(next_line, next_line + len(frame))
                next_line += len(frame)
                yield frame[list(BAR_COLUMNS)]
        except pd.errors.ParserError as exc:
            raise InvalidOperationError(f"Malformed CSV: {exc}") from exc
