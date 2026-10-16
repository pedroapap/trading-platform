"""Trading days: which day of its market's sessions each bar belongs to, in the market's own
time zone."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.strategies.definition import Session
from app.strategies.rules import minutes

_NS_PER_MINUTE = 60_000_000_000
_MINUTES_PER_DAY = 24 * 60


@dataclass(frozen=True)
class Calendar:
    """Each bar's place in the trading days: the day it belongs to (a local date, as days
    since 1970-01-01), when it starts (minutes after local midnight), and whether it overlaps
    the session at all. `elapsed` counts its start from the midnight that begins its trading
    day instead, so it is negative for a bar that starts the evening before. Bars last `width`
    minutes."""

    day: np.ndarray
    minute: np.ndarray
    in_session: np.ndarray
    elapsed: np.ndarray
    width: int


def calendar(times: pd.DatetimeIndex, session: Session | None) -> Calendar:
    """The calendar of bars starting at `times` (UTC, in order). A bar lasts as long as the
    shortest spacing between them, so one that starts before the open can still overlap the
    session (an hourly bar at 09:00 overlaps a 09:30 open), and a bar that starts late on one
    local day can belong to the next day's session (a daily bar starting at 00:00 UTC is
    19:00 the evening before in New York)."""
    session = session or Session()
    wall = times.tz_convert(session.timezone).tz_localize(None).as_unit("ns").asi8
    elapsed = wall // _NS_PER_MINUTE
    date, minute = elapsed // _MINUTES_PER_DAY, elapsed % _MINUTES_PER_DAY
    width = _width(times)
    end = minute + width
    opens, closes = minutes(session.start), minutes(session.end)
    today = (minute < closes) & (end > opens)
    tomorrow = ~today & (end > _MINUTES_PER_DAY + opens)
    return Calendar(
        day=date + tomorrow,
        minute=minute,
        in_session=today | tomorrow,
        elapsed=minute - _MINUTES_PER_DAY * tomorrow,
        width=width,
    )


def _width(times: pd.DatetimeIndex) -> int:
    """How long each bar lasts, in minutes: the shortest spacing between bars, and at least a
    minute."""
    if len(times) < 2:
        return 1
    return max(int(np.diff(times.as_unit("ns").asi8).min() // _NS_PER_MINUTE), 1)
