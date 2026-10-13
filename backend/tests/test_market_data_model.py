from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.market_data.timeframes import Timeframe
from app.models import MarketData

TS = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)


def bar(**overrides: object) -> MarketData:
    values: dict[str, object] = {
        "symbol": "BTCUSD",
        "timeframe": Timeframe.M1,
        "ts": TS,
        "open": Decimal("100"),
        "high": Decimal("105"),
        "low": Decimal("99"),
        "close": Decimal("104"),
        "volume": Decimal("1.5"),
        "source": "test",
    }
    return MarketData(**(values | overrides))


def test_market_data_is_a_hypertable(db_session):
    query = text(
        "SELECT count(*) FROM timescaledb_information.hypertables"
        " WHERE hypertable_name = 'market_data'"
    )

    assert db_session.scalar(query) == 1


def test_a_valid_bar_is_stored(db_session):
    stored = bar()
    db_session.add(stored)
    db_session.flush()
    db_session.refresh(stored)

    assert stored.imported_at is not None


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        ({"high": Decimal("103")}, "ck_market_data_ohlc_consistent"),  # high below the close
        ({"low": Decimal("101")}, "ck_market_data_ohlc_consistent"),  # low above the open
        ({"open": Decimal("0"), "low": Decimal("0")}, "ck_market_data_prices_positive"),
        ({"volume": Decimal("-1")}, "ck_market_data_volume_non_negative"),
    ],
)
def test_inconsistent_bars_are_rejected(db_session, overrides, constraint):
    db_session.add(bar(**overrides))

    with pytest.raises(IntegrityError, match=constraint):
        db_session.flush()


def test_unknown_timeframe_is_rejected(db_session):
    insert = text(
        "INSERT INTO market_data (symbol, timeframe, ts, open, high, low, close, volume, source)"
        " VALUES ('BTCUSD', '2m', now(), 1, 1, 1, 1, 0, 'test')"
    )

    with pytest.raises(IntegrityError, match="ck_market_data_timeframe"):
        db_session.execute(insert)


def test_a_bar_is_unique_per_symbol_timeframe_and_time(db_session):
    db_session.add_all([bar(), bar(timeframe=Timeframe.H1), bar(symbol="ETHUSD")])
    db_session.flush()

    db_session.add(bar(close=Decimal("100")))
    with pytest.raises(IntegrityError, match="pk_market_data"):
        db_session.flush()
