"""Bars built from finer stored bars. Data is chosen so expected values are easy to derive."""

import io
from datetime import UTC, datetime, timedelta

import pytest

from app.errors import InvalidOperationError
from app.market_data.timeframes import Timeframe
from app.schemas.market_data import BarQuery
from app.services.market_data import get_bars, import_bars

START = datetime(2026, 1, 5, tzinfo=UTC)


def store(db, symbol: str, step: timedelta, count: int) -> None:
    """Bar i: open 100+i, high 101+i, low 99+i, close 100.5+i, volume 1."""
    lines = ["timestamp,open,high,low,close,volume"]
    for i in range(count):
        ts = (START + i * step).isoformat()
        lines.append(f"{ts},{100 + i},{101 + i},{99 + i},{100.5 + i},1")
    import_bars(db, io.StringIO("\n".join(lines) + "\n"), symbol)


def query(db, symbol: str, timeframe: str, **kwargs) -> tuple[list[tuple], Timeframe | None]:
    result = get_bars(db, symbol, BarQuery(timeframe=timeframe, **kwargs))
    rows = [
        (
            bar.ts,
            float(bar.open),
            float(bar.high),
            float(bar.low),
            float(bar.close),
            float(bar.volume),
        )
        for bar in result.bars
    ]
    return rows, result.aggregated_from


def test_hourly_bars_from_minutes(db_session):
    store(db_session, "BTCUSD", timedelta(minutes=1), 120)

    rows, source = query(db_session, "BTCUSD", "1h")

    assert source is Timeframe.M1
    assert rows == [
        (START, 100, 160, 99, 159.5, 60),  # minutes 0-59
        (START + timedelta(hours=1), 160, 220, 159, 219.5, 60),  # minutes 60-119
    ]


def test_daily_bars_use_the_coarsest_source(db_session):
    store(db_session, "BTCUSD", timedelta(minutes=1), 120)
    store(db_session, "BTCUSD", timedelta(hours=1), 48)

    rows, source = query(db_session, "BTCUSD", "1d")

    assert source is Timeframe.H1
    assert rows == [
        (START, 100, 124, 99, 123.5, 24),  # hours 0-23
        (START + timedelta(days=1), 124, 148, 123, 147.5, 24),  # hours 24-47
    ]


def test_stored_timeframes_are_returned_as_is(db_session):
    store(db_session, "BTCUSD", timedelta(hours=1), 3)

    rows, source = query(db_session, "BTCUSD", "1h")

    assert source is None
    assert len(rows) == 3


def test_an_unaligned_start_skips_the_partial_first_bar(db_session):
    store(db_session, "BTCUSD", timedelta(minutes=1), 120)

    rows, _ = query(db_session, "BTCUSD", "1h", start=START + timedelta(minutes=30))

    assert [row[0] for row in rows] == [START + timedelta(hours=1)]


def test_finer_than_stored_is_refused(db_session):
    store(db_session, "BTCUSD", timedelta(days=1), 3)

    with pytest.raises(InvalidOperationError, match=r"no 1h bars, or finer bars .* \(stored: 1d\)"):
        query(db_session, "BTCUSD", "1h")


def test_aggregated_bars_through_the_api(db_session, client, auth_headers):
    store(db_session, "BTCUSD", timedelta(minutes=1), 120)

    body = client.get(
        "/api/market-data/btcusd/bars", params={"timeframe": "1h"}, headers=auth_headers
    ).json()

    assert body["aggregated_from"] == "1m"
    assert body["bars"][0] == {
        "ts": "2026-01-05T00:00:00Z",
        "open": "100",
        "high": "160",
        "low": "99",
        "close": "159.5",
        "volume": "60",
    }
