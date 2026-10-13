import io
from pathlib import Path

import pandas as pd
import pytest

from app.errors import InvalidOperationError
from app.market_data import formats
from app.market_data.formats.generic import GenericOhlcvFormat

FIXTURES = Path(__file__).parent / "fixtures"
GENERIC = GenericOhlcvFormat()


def read_all(text: str, chunk_rows: int = 1000) -> pd.DataFrame:
    return pd.concat(GENERIC.read(io.StringIO(text), chunk_rows))


@pytest.mark.parametrize("fixture", ["daily_tradingview.csv", "daily_yahoo.csv"])
def test_common_layouts_parse_to_identical_bars(fixture):
    expected = read_all((FIXTURES / "daily_generic.csv").read_text())

    parsed = read_all((FIXTURES / fixture).read_text())

    pd.testing.assert_frame_equal(parsed, expected)
    assert expected["ts"].iloc[0] == pd.Timestamp("2026-01-05", tz="UTC")
    assert expected["close"].tolist() == ["93850", "94900.1", "94100"]
    assert expected["volume"].iloc[0] == "1234.56789"  # exact text, never a float


def test_the_generic_format_is_registered_and_detected():
    sample = (FIXTURES / "daily_yahoo.csv").read_text()

    assert isinstance(formats.detect(sample), GenericOhlcvFormat)
    assert "generic_ohlcv" in formats.available()


def test_epoch_milliseconds_semicolons_and_missing_volume():
    bars = read_all("Time;Open;High;Low;Close\n1767571260000;1;2;0.5;1.5\n")

    assert bars["ts"].iloc[0] == pd.Timestamp("2026-01-05 00:01", tz="UTC")
    assert bars["volume"].iloc[0] == "0"


def test_unparseable_timestamps_become_missing():
    bars = read_all("date,open,high,low,close\nnot-a-date,1,2,0.5,1.5\n")

    assert pd.isna(bars["ts"].iloc[0])


def test_chunks_are_indexed_by_file_line_number():
    rows = "".join(f"2026-01-0{day}T00:00Z,1,2,0.5,1.5,10\n" for day in (5, 6, 7))
    text = "timestamp,open,high,low,close,volume\n" + rows

    chunks = list(GENERIC.read(io.StringIO(text), chunk_rows=2))

    assert [list(chunk.index) for chunk in chunks] == [[2, 3], [4]]


def test_a_header_without_prices_is_not_this_format():
    text = "timestamp,price,volume\n2026-01-05,1,2\n"

    assert not GENERIC.sniff(text)
    with pytest.raises(InvalidOperationError, match="needs a time/date column"):
        read_all(text)
