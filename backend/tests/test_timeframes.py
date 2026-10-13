from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.market_data.timeframes import Timeframe


def test_seconds_and_lookup_round_trip():
    assert [tf.seconds for tf in Timeframe] == [60, 300, 900, 1800, 3600, 14400, 86400]
    assert all(Timeframe.from_seconds(tf.seconds) is tf for tf in Timeframe)
    assert Timeframe.from_seconds(120) is None


@pytest.mark.parametrize(
    ("timeframe", "ts", "aligned"),
    [
        (Timeframe.M1, datetime(2026, 1, 5, 14, 31, tzinfo=UTC), True),
        (Timeframe.M1, datetime(2026, 1, 5, 14, 31, 30, tzinfo=UTC), False),
        (Timeframe.M5, datetime(2026, 1, 5, 14, 35, tzinfo=UTC), True),
        (Timeframe.M5, datetime(2026, 1, 5, 14, 31, tzinfo=UTC), False),
        (Timeframe.H4, datetime(2026, 1, 5, 8, tzinfo=UTC), True),
        (Timeframe.H4, datetime(2026, 1, 5, 9, tzinfo=UTC), False),
        (Timeframe.D1, datetime(2026, 1, 5, tzinfo=UTC), True),
        # midnight in New York is 05:00 UTC, which is not a UTC day boundary
        (Timeframe.D1, datetime(2026, 1, 5, tzinfo=timezone(timedelta(hours=-5))), False),
    ],
)
def test_alignment_is_relative_to_the_epoch_in_utc(timeframe, ts, aligned):
    assert timeframe.is_aligned(ts) is aligned


def test_divides():
    assert Timeframe.M1.divides(Timeframe.H1)
    assert Timeframe.M15.divides(Timeframe.H4)
    assert Timeframe.H4.divides(Timeframe.D1)
    assert not Timeframe.H1.divides(Timeframe.M15)
    assert Timeframe.D1.divides(Timeframe.D1)
