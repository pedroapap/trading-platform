import io
from pathlib import Path

import pandas as pd

from app.market_data import formats
from app.market_data.formats.binance import BinanceKlinesFormat

FIXTURE = (Path(__file__).parent / "fixtures" / "binance_1m.csv").read_text()
BINANCE = BinanceKlinesFormat()


def test_binance_files_are_detected():
    assert isinstance(formats.detect(FIXTURE), BinanceKlinesFormat)
    assert not BINANCE.sniff("open_time,open,high,low,close,volume\n")


def test_klines_are_read_as_bars():
    bars = pd.concat(BINANCE.read(io.StringIO(FIXTURE), chunk_rows=2))

    assert list(bars.index) == [1, 2, 3]
    assert bars["ts"].tolist() == [
        pd.Timestamp("2026-01-05 00:00", tz="UTC"),
        pd.Timestamp("2026-01-05 00:01", tz="UTC"),
        pd.Timestamp("2026-01-05 00:02", tz="UTC"),
    ]
    assert bars.iloc[0][["open", "high", "low", "close", "volume"]].tolist() == [
        "93000.50",
        "93010.00",
        "92990.10",
        "93005.00",
        "12.50000000",
    ]


def test_microsecond_open_times_from_2025_spot_files():
    line = "1767571200000000,1,2,0.5,1.5,10,1767571259999999,15,3,5,7.5,0\n"

    bars = next(BINANCE.read(io.StringIO(line), chunk_rows=10))

    assert bars["ts"].iloc[0] == pd.Timestamp("2026-01-05 00:00", tz="UTC")
