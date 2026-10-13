"""Pluggable price-file formats.

A format turns one kind of file into chunks of normalized bars. To support a new source,
implement `PriceFileFormat` and `register()` it here; imports can then name it explicitly
or rely on `detect()`, which asks each registered format to recognise the file's first lines.
"""

from app.market_data.formats.base import (
    BAR_COLUMNS,
    SAMPLE_LINES,
    PriceFileFormat,
    UnknownFormatError,
    available,
    detect,
    get_format,
    register,
)
from app.market_data.formats.binance import BinanceKlinesFormat
from app.market_data.formats.generic import GenericOhlcvFormat

# Detection tries formats in this order.
register(GenericOhlcvFormat())
register(BinanceKlinesFormat())

__all__ = [
    "BAR_COLUMNS",
    "SAMPLE_LINES",
    "PriceFileFormat",
    "UnknownFormatError",
    "available",
    "detect",
    "get_format",
    "register",
]
