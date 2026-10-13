import io
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.errors import InvalidOperationError
from app.market_data.timeframes import Timeframe
from app.models import MarketData
from app.services.market_data import import_bars

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> io.StringIO:
    return io.StringIO((FIXTURES / name).read_text())


def stored(db) -> int:
    return db.scalar(select(func.count()).select_from(MarketData))


def test_import_stores_validated_bars(db_session):
    summary = import_bars(db_session, fixture("binance_1m.csv"), " btcusdt ")

    assert (summary.symbol, summary.timeframe, summary.format) == (
        "BTCUSDT",
        Timeframe.M1,
        "binance_klines",
    )
    assert (summary.inserted, summary.duplicates, summary.rejected) == (3, 0, 0)
    assert summary.first_ts == datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    assert summary.last_ts == datetime(2026, 1, 5, 0, 2, tzinfo=UTC)
    bar = db_session.get(MarketData, ("BTCUSDT", Timeframe.M1, summary.first_ts))
    assert (bar.open, bar.volume, bar.source) == (
        Decimal("93000.5"),
        Decimal("12.5"),
        "binance_klines",
    )


def test_importing_the_same_file_twice_only_adds_duplicates(db_session):
    import_bars(db_session, fixture("binance_1m.csv"), "BTCUSDT")

    again = import_bars(db_session, fixture("binance_1m.csv"), "BTCUSDT")

    assert (again.inserted, again.duplicates) == (0, 3)
    assert stored(db_session) == 3


def test_invalid_rows_are_reported_and_valid_ones_kept(db_session):
    text = (
        "timestamp,open,high,low,close,volume\n"
        "2026-01-05T00:00Z,100,105,99,104,1\n"
        "2026-01-05T00:01Z,100,103,99,104,1\n"  # high below the close
        "2026-01-05T00:02Z,104,106,103,105,2\n"
    )

    summary = import_bars(db_session, io.StringIO(text), "BTCUSD")

    assert (summary.inserted, summary.rejected) == (2, 1)
    assert summary.rejections[0].line == 3
    assert "low/high do not bracket" in summary.rejections[0].reason


def test_daily_files_are_stored_as_daily_bars(db_session):
    summary = import_bars(db_session, fixture("daily_yahoo.csv"), "BTCUSD")

    assert (summary.timeframe, summary.format, summary.inserted) == (
        Timeframe.D1,
        "generic_ohlcv",
        3,
    )


def test_a_requested_timeframe_must_match_the_data(db_session):
    with pytest.raises(InvalidOperationError, match="1d apart, but timeframe 1h was requested"):
        import_bars(db_session, fixture("daily_yahoo.csv"), "BTCUSD", timeframe=Timeframe.H1)

    assert stored(db_session) == 0


def test_an_explicit_format_is_used(db_session):
    with pytest.raises(InvalidOperationError, match="needs a time/date column"):
        import_bars(db_session, fixture("binance_1m.csv"), "BTCUSD", format_name="generic_ohlcv")


@pytest.mark.parametrize(
    ("content", "symbol", "message"),
    [
        ("timestamp,open,high,low,close\n", "BTCUSD", "The file has no bars"),
        ("", "BTCUSD", "Could not recognise the file format"),
        ("timestamp,open,high,low,close\n2026-01-05,1,1,1,1\n", "BTC USD", "Invalid symbol"),
    ],
)
def test_unusable_imports_are_refused(db_session, content, symbol, message):
    with pytest.raises(InvalidOperationError, match=message):
        import_bars(db_session, io.StringIO(content), symbol, timeframe=Timeframe.D1)
