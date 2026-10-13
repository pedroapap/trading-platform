"""Pluggable price-file formats.

A format turns one kind of file into chunks of normalized bars. To support a new source,
implement `PriceFileFormat` and `register()` it; imports can then name it explicitly or
rely on `detect()`, which asks each registered format to recognise the file's first lines.
"""

from collections.abc import Iterator
from typing import Protocol, TextIO

import pandas as pd

from app.errors import InvalidOperationError

# Columns of every chunk a format yields: `ts` as UTC timestamps; prices and volume as the
# file's original text, so no precision is lost before validation converts them to Decimal.
BAR_COLUMNS = ("ts", "open", "high", "low", "close", "volume")

SAMPLE_LINES = 5


class PriceFileFormat(Protocol):
    name: str
    description: str

    def sniff(self, sample: str) -> bool:
        """Whether the file's first lines look like this format."""
        ...

    def read(self, stream: TextIO, chunk_rows: int) -> Iterator[pd.DataFrame]:
        """Yield the file as DataFrames with BAR_COLUMNS, `chunk_rows` rows at a time."""
        ...


class UnknownFormatError(InvalidOperationError):
    pass


_FORMATS: dict[str, PriceFileFormat] = {}


def register(fmt: PriceFileFormat) -> PriceFileFormat:
    _FORMATS[fmt.name] = fmt
    return fmt


def available() -> list[str]:
    return list(_FORMATS)


def get_format(name: str) -> PriceFileFormat:
    try:
        return _FORMATS[name]
    except KeyError:
        raise UnknownFormatError(
            f"Unknown file format {name!r}; supported: {', '.join(available())}"
        ) from None


def detect(sample: str) -> PriceFileFormat:
    """The first registered format that recognises `sample` (the file's first lines)."""
    for fmt in _FORMATS.values():
        if fmt.sniff(sample):
            return fmt
    raise UnknownFormatError(
        "Could not recognise the file format; pass the format explicitly"
        f" (supported: {', '.join(available())})"
    )
