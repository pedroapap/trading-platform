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
    monkeypatch.setattr("app.market_data.formats.base._FORMATS", {})
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


def test_parse_timestamps_accepts_iso_text_and_epochs_in_any_unit():
    raw = pd.Series(
        [
            "2026-01-05T00:01:00Z",
            "2026-01-05 01:01:00+01:00",
            "2026-01-05 00:01",  # naive means UTC
            "1767571260",  # seconds
            "1767571260000",  # milliseconds
            "1767571260000000",  # microseconds
            "1767571260000000000",  # nanoseconds
        ]
    )

    parsed = formats.base.parse_timestamps(raw)

    assert parsed.dtype == "datetime64[us, UTC]"
    assert (parsed == pd.Timestamp("2026-01-05 00:01", tz="UTC")).all()
