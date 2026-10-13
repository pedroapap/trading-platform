"""Binance kline files from data.binance.vision: no header, 12 columns.

Columns: open_time, open, high, low, close, volume, close_time, quote_volume, trade count,
taker buy base volume, taker buy quote volume, ignore. `open_time` is epoch milliseconds,
or microseconds for spot data from 2025 on. Files that do have a header row are read by
the generic format instead.
"""

import re
from collections.abc import Iterator
from typing import TextIO

import pandas as pd

from app.errors import InvalidOperationError
from app.market_data.formats.base import BAR_COLUMNS, parse_timestamps

_FIELDS = 12
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


class BinanceKlinesFormat:
    name = "binance_klines"
    description = "Binance kline CSV from data.binance.vision (no header row, 12 columns)"

    def sniff(self, sample: str) -> bool:
        fields = sample.lstrip().partition("\n")[0].strip().split(",")
        return (
            len(fields) == _FIELDS
            and fields[0].isdigit()
            and all(_NUMBER.match(field) for field in fields[1:6])
        )

    def read(self, stream: TextIO, chunk_rows: int) -> Iterator[pd.DataFrame]:
        chunks = pd.read_csv(
            stream,
            header=None,
            usecols=range(len(BAR_COLUMNS)),
            names=range(_FIELDS),
            dtype=str,
            keep_default_na=False,
            chunksize=chunk_rows,
        )
        next_line = 1
        try:
            for chunk in chunks:
                frame = chunk.set_axis(list(BAR_COLUMNS), axis="columns")
                frame["ts"] = parse_timestamps(frame["ts"])
                frame.index = pd.RangeIndex(next_line, next_line + len(frame))
                next_line += len(frame)
                yield frame
        except pd.errors.ParserError as exc:
            raise InvalidOperationError(f"Malformed Binance kline file: {exc}") from exc
