"""The price-file format interface, its registry and shared parsing helpers."""

from collections.abc import Iterator
from typing import Protocol, TextIO

import pandas as pd

from app.errors import InvalidOperationError

# Columns of every chunk a format yields: `ts` as UTC timestamps (NaT if unparseable);
# prices and volume as the file's original text, so no precision is lost before validation
# converts them to Decimal. The index is the 1-based line number in the file.
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


# Epoch numbers are read in the largest unit that keeps them below these magnitudes, so
# seconds, milliseconds, microseconds and nanoseconds can all be recognised.
_EPOCH_UNITS = (("s", 1e11), ("ms", 1e14), ("us", 1e17), ("ns", float("inf")))


def parse_timestamps(raw: pd.Series) -> pd.Series:
    """ISO 8601 text (naive means UTC) or epoch numbers in any unit, as UTC timestamps."""
    numbers = pd.to_numeric(raw, errors="coerce")
    is_number = numbers.notna()
    parsed = pd.to_datetime(raw.where(~is_number), utc=True, errors="coerce", format="ISO8601")
    # Microseconds, like Postgres timestamptz, whatever resolution pandas inferred.
    parsed = parsed.astype("datetime64[us, UTC]")
    remaining = is_number
    for unit, limit in _EPOCH_UNITS:
        in_unit = remaining & (numbers.abs() < limit)
        if in_unit.any():
            parsed[in_unit] = pd.to_datetime(numbers[in_unit], unit=unit, utc=True)
        remaining &= ~in_unit
    return parsed
