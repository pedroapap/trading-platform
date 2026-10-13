import io
from collections.abc import Iterator

import pandas as pd
import pytest

from app.market_data import formats
from app.market_data.formats import BAR_COLUMNS, UnknownFormatError


class PipeFormat:
    """Stub format for registry tests: lines like `|2026-01-05T00:00Z|1|2|0.5|1.5|10`."""

    name = "pipes"
    description = "Pipe-separated test format"

    def sniff(self, sample: str) -> bool:
        return sample.startswith("|")

    def read(self, stream, chunk_rows: int) -> Iterator[pd.DataFrame]:
        rows = [line.strip("|\n").split("|") for line in stream]
        frame = pd.DataFrame(rows, columns=BAR_COLUMNS)
        frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
        yield frame


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.setattr(formats, "_FORMATS", {})
    return formats.register(PipeFormat())


def test_registered_formats_can_be_listed_and_looked_up(registry):
    assert formats.available() == ["pipes"]
    assert formats.get_format("pipes") is registry


def test_detect_picks_the_format_that_recognises_the_sample(registry):
    sample = "|2026-01-05T00:00Z|1|2|0.5|1.5|10\n"

    fmt = formats.detect(sample)
    chunk = next(fmt.read(io.StringIO(sample), chunk_rows=100))

    assert fmt is registry
    assert list(chunk.columns) == list(BAR_COLUMNS)
    assert chunk["close"].tolist() == ["1.5"]


def test_unknown_names_and_unrecognised_files_are_errors(registry):
    with pytest.raises(UnknownFormatError, match="Unknown file format 'csv'; supported: pipes"):
        formats.get_format("csv")
    with pytest.raises(UnknownFormatError, match="Could not recognise the file format"):
        formats.detect("time,open,high,low,close\n")
