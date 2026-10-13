"""Bars loaded for a backtest: what get_bars returns, as floats, without a row limit."""

import io
from datetime import UTC, datetime, timedelta

import pytest

from app.errors import InvalidOperationError
from app.market_data.timeframes import Timeframe
from app.schemas.market_data import BarQuery
from app.services.market_data import get_bars, import_bars, load_bars

START = datetime(2026, 1, 5, tzinfo=UTC)


def store(db, count: int) -> None:
    """`count` one-minute BTCUSD bars from START."""
    lines = ["timestamp,open,high,low,close,volume"]
    for i in range(count):
        ts = (START + timedelta(minutes=i)).isoformat()
        lines.append(f"{ts},{100 + i},{101 + i},{99 + i},{100.5 + i},{1 + i % 3}")
    import_bars(db, io.StringIO("\n".join(lines) + "\n"), "BTCUSD")


@pytest.mark.parametrize("timeframe", [Timeframe.M1, Timeframe.H1], ids=["stored", "aggregated"])
def test_bars_match_get_bars(db_session, timeframe):
    store(db_session, 180)

    bars = load_bars(db_session, "btcusd", timeframe)

    expected = get_bars(db_session, "BTCUSD", BarQuery(timeframe=timeframe)).bars
    assert bars.index.tolist() == [bar.ts for bar in expected]
    assert bars.to_numpy().tolist() == [
        [float(bar.open), float(bar.high), float(bar.low), float(bar.close), float(bar.volume)]
        for bar in expected
    ]
    assert list(bars.columns) == ["open", "high", "low", "close", "volume"]
    assert str(bars.index.tz) == "UTC"


def test_there_is_no_row_limit(db_session):
    store(db_session, 10_001)

    assert len(load_bars(db_session, "BTCUSD", Timeframe.M1)) == 10_001


def test_the_range_is_half_open(db_session):
    store(db_session, 10)

    bars = load_bars(
        db_session,
        "BTCUSD",
        Timeframe.M1,
        START + timedelta(minutes=2),
        START + timedelta(minutes=5),
    )

    assert bars.index.tolist() == [START + timedelta(minutes=m) for m in (2, 3, 4)]


def test_a_range_without_bars_is_an_error(db_session):
    store(db_session, 10)

    with pytest.raises(InvalidOperationError, match="There are no BTCUSD bars in this range"):
        load_bars(db_session, "BTCUSD", Timeframe.M1, start=START + timedelta(days=1))
