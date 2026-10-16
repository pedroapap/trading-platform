import pandas as pd
import pytest

from app.backtest.sessions import calendar
from app.strategies.definition import Session

NEW_YORK = Session(timezone="America/New_York", start="09:30", end="16:00")


def at(*times: str) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(times, tz="UTC")


def dates(days) -> list[str]:
    return pd.to_datetime(days, unit="D").strftime("%Y-%m-%d").tolist()


# Half-hour bars at 09:00, 09:30, 15:30 and 16:00 New York time, on a Friday and a Monday.
# fmt: off
# Clocks went forward on Sunday 8 March 2026: the Friday is UTC-5, the Monday UTC-4.
SPRING = [
    "2026-03-06 14:00", "2026-03-06 14:30", "2026-03-06 20:30", "2026-03-06 21:00",
    "2026-03-09 13:00", "2026-03-09 13:30", "2026-03-09 19:30", "2026-03-09 20:00",
]
# They went back on Sunday 1 November 2026: the Friday is UTC-4, the Monday UTC-5.
AUTUMN = [
    "2026-10-30 13:00", "2026-10-30 13:30", "2026-10-30 19:30", "2026-10-30 20:00",
    "2026-11-02 14:00", "2026-11-02 14:30", "2026-11-02 20:30", "2026-11-02 21:00",
]
# fmt: on


@pytest.mark.parametrize(
    ("days", "times"),
    [(["2026-03-06", "2026-03-09"], SPRING), (["2026-10-30", "2026-11-02"], AUTUMN)],
)
def test_the_new_york_session_follows_daylight_saving(days, times):
    found = calendar(at(*times), NEW_YORK)

    assert found.minute.tolist() == [540, 570, 930, 960] * 2
    assert found.in_session.tolist() == [False, True, True, False] * 2
    assert dates(found.day) == [days[0]] * 4 + [days[1]] * 4


def test_an_hourly_bar_starting_before_the_open_overlaps_the_session():
    # 09:00 to 10:00 New York time contains the 09:30 open; 16:00 to 17:00 starts at the close.
    found = calendar(at("2026-03-06 14:00", "2026-03-06 15:00", "2026-03-06 21:00"), NEW_YORK)

    assert found.in_session.tolist() == [True, True, False]


def test_daily_bars_belong_to_the_session_of_their_utc_day():
    # A daily bar starts at 00:00 UTC, which is 19:00 the evening before in New York.
    found = calendar(at("2026-03-05", "2026-03-06", "2026-03-09"), NEW_YORK)

    assert found.in_session.all()
    assert dates(found.day) == ["2026-03-05", "2026-03-06", "2026-03-09"]


def test_without_a_session_the_trading_day_is_the_utc_day():
    found = calendar(at("2026-03-06 23:58", "2026-03-06 23:59", "2026-03-07 00:00"), None)

    assert found.in_session.all()
    assert dates(found.day) == ["2026-03-06", "2026-03-06", "2026-03-07"]
    assert found.minute.tolist() == [1438, 1439, 0]


def test_a_bar_reaching_into_the_next_days_session_belongs_to_that_day():
    # Four-hour bars against a 00:00 to 06:00 UTC session: the bar from 22:00 runs into it.
    session = Session(start="00:00", end="06:00")

    found = calendar(at("2026-03-06 18:00", "2026-03-06 22:00", "2026-03-07 02:00"), session)

    assert found.in_session.tolist() == [False, True, True]
    assert dates(found.day[1:]) == ["2026-03-07", "2026-03-07"]
    # The bar from 22:00 starts two hours before its trading day.
    assert found.elapsed.tolist() == [1080, -120, 120]


def test_a_session_in_another_time_zone_crosses_utc_midnight():
    # Tokyo trades from 09:00 to 15:00 local time, which starts at 00:00 UTC.
    tokyo = Session(timezone="Asia/Tokyo", start="09:00", end="15:00")

    found = calendar(at("2026-03-05 23:30", "2026-03-06 00:00", "2026-03-06 05:30"), tokyo)

    assert found.in_session.tolist() == [False, True, True]
    assert dates(found.day[1:]) == ["2026-03-06", "2026-03-06"]


def test_a_single_bar_is_in_the_session_it_starts_in():
    assert calendar(at("2026-03-06 00:00"), None).in_session.tolist() == [True]
    assert calendar(at("2026-03-06 21:00"), NEW_YORK).in_session.tolist() == [False]
