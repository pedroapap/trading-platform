"""Rebuild the docs' sample prices: a year of made-up hourly bars for the symbol DEMOUSDT.

The prices are synthetic, not a real market's. They are a seeded random walk pulled toward a
level that drifts around 100 month by month, with a few double bottoms and breakouts planted
in it so that the docs' example strategies trade. The script uses only the standard library
and plain arithmetic, so it writes the same bytes on every machine:

    python docs/sample-data/generate.py            # writes demousdt-1h.csv
    python docs/sample-data/generate.py --minutes  # also demousdt-1m.csv, inside those hours

The 1-minute file (about 29 MB) isn't kept in the repository.
"""

import argparse
import itertools
import random
from collections import deque
from datetime import UTC, datetime, timedelta
from pathlib import Path

SEED = 20250101
START = datetime(2025, 1, 1, tzinfo=UTC)
HOURS = 365 * 24
# The level the price is pulled toward at the start of each month, moving in a straight line
# to the next month's; the last is where it heads at the end of the year.
WAYPOINTS = [100, 108, 97, 104, 93, 101, 112, 104, 96, 103, 117, 108, 100]
PULL = 0.01  # share of the gap to the level closed each hour
VOLATILITY = 0.005  # of each hour's random move

# A double bottom, as multiples of the close before it: a slide, a low, a bounce, a second low
# 0.2% above the first, then a rally. Planted when the 50-hour average crosses below 100.
# fmt: off
DOUBLE_BOTTOM = [
    (1.0000, 1.0033, 0.9889, 0.9911), (0.9911, 0.9933, 0.9844, 0.9867),
    (0.9867, 0.9889, 0.9822, 0.9833), (0.9833, 0.9856, 0.9800, 0.9811),
    (0.9811, 0.9833, 0.9789, 0.9800), (0.9800, 0.9844, 0.9778, 0.9833),
    (0.9833, 0.9944, 0.9822, 0.9922), (0.9922, 1.0056, 0.9911, 1.0033),
    (1.0033, 1.0111, 1.0000, 1.0089), (1.0089, 1.0100, 1.0000, 1.0011),
    (1.0011, 1.0022, 0.9933, 0.9944), (0.9944, 0.9956, 0.9878, 0.9889),
    (0.9889, 0.9900, 0.9844, 0.9856), (0.9856, 0.9867, 0.9822, 0.9833),
    (0.9833, 0.9844, 0.9811, 0.9822), (0.9822, 0.9856, 0.9800, 0.9844),
    (0.9844, 0.9933, 0.9833, 0.9911), (0.9911, 0.9989, 0.9900, 0.9967),
    (0.9967, 1.0000, 0.9933, 0.9944), (0.9944, 0.9956, 0.9822, 0.9889),
    (0.9889, 0.9944, 0.9867, 0.9922), (0.9922, 1.0000, 0.9911, 0.9989),
    (0.9989, 1.0100, 0.9978, 1.0056), (1.0056, 1.0089, 1.0033, 1.0067),
    (1.0067, 1.0100, 1.0044, 1.0078),
]
# fmt: on
# A breakout, as multiples of the close before it: 22 hours in a 0.7% range, then a move up
# through it. Planted in an uptrend (the 20-hour average 0.3% above the 50-hour one).
QUIET = [1.000, 1.002, 0.999, 1.001, 0.998, 1.000, 1.002, 1.001, 0.999, 1.000, 1.002]
RISE = [1.011, 1.016, 1.014, 1.021, 1.026, 1.024, 1.031]
DOUBLE_BOTTOMS, BREAKOUTS = 5, 4
# The fewest hours between two plants of a kind.
APART = {"double bottom": 24 * 21, "breakout": 24 * 70}


def breakout_bars() -> list[tuple[float, float, float, float]]:
    closes = QUIET + list(reversed(QUIET)) + RISE
    bars, before = [], 1.0
    for close in closes:
        wick = 0.002 if close > 1.005 else 0.0015
        bars.append((before, max(before, close) + wick, min(before, close) - wick, close))
        before = close
    return bars


def cents(price: float) -> int:
    return int(price * 100 + 0.5)


def normal(rng: random.Random) -> float:
    """About normal, with mean 0 and deviation 1: the sum of 12 uniforms, less 6."""
    return sum(rng.random() for _ in range(12)) - 6


def month_start(index: int) -> datetime:
    """The first day of the year's month `index` (0 is January, 12 the next January)."""
    return datetime(START.year + index // 12, index % 12 + 1, 1, tzinfo=UTC)


def level(hour: int) -> float:
    """The level the price is pulled toward: straight lines between the monthly waypoints."""
    now = START + timedelta(hours=hour)
    month = now.month - 1
    into = (now - month_start(month)) / (month_start(month + 1) - month_start(month))
    return WAYPOINTS[month] + (WAYPOINTS[month + 1] - WAYPOINTS[month]) * into


def hourly_bars() -> tuple[list[tuple[datetime, int, int, int, int, int]], list[str]]:
    """Each hour's start, open, high, low and close in cents, and volume in 1/10,000s; and
    what was planted where."""
    rng = random.Random(SEED)
    rows, plants = [], []
    closes: deque[float] = deque(maxlen=50)
    fast = slow = close = 100.0
    plans: list[tuple[float, float, float, float]] = []
    planted = {"double bottom": 0, "breakout": 0}
    last = {kind: -apart for kind, apart in APART.items()}
    previous_average = None
    for hour in range(HOURS):
        average = sum(closes) / len(closes) if len(closes) == 50 else None
        if not plans and average is not None and previous_average is not None:
            if (
                previous_average >= 100 > average
                and planted["double bottom"] < DOUBLE_BOTTOMS
                and hour - last["double bottom"] >= APART["double bottom"]
                and hour - last["breakout"] >= 24 * 7
            ):
                plans = [tuple(close * part for part in bar) for bar in DOUBLE_BOTTOM]
                planted["double bottom"] += 1
                plants.append(f"double bottom from {START + timedelta(hours=hour):%Y-%m-%d %H:%M}")
                last["double bottom"] = hour
            elif (
                fast > slow * 1.003
                and planted["breakout"] < BREAKOUTS
                and hour - last["breakout"] >= APART["breakout"]
                and hour - last["double bottom"] >= 24 * 7
                and hour >= 24 * 30
            ):
                plans = [tuple(close * part for part in bar) for bar in breakout_bars()]
                planted["breakout"] += 1
                plants.append(f"breakout from {START + timedelta(hours=hour):%Y-%m-%d %H:%M}")
                last["breakout"] = hour
        previous_average = average
        if plans:
            open_, high, low, close = plans.pop(0)
            move = close / open_ - 1
        else:
            open_ = close
            move = PULL * (level(hour) - open_) / open_ + VOLATILITY * normal(rng)
            close = open_ * (1 + move)
            high = max(open_, close) * (1 + VOLATILITY * 0.6 * rng.random())
            low = min(open_, close) * (1 - VOLATILITY * 0.6 * rng.random())
        o, c = cents(open_), cents(close)
        h, l_ = max(cents(high), o, c), min(cents(low), o, c)
        # Busier in the European and American afternoon, and on big moves.
        hour_of_day = hour % 24
        busy = 1.6 if 12 <= hour_of_day < 21 else 1.0
        volume = int((300 + 40_000 * abs(move)) * busy * (0.6 + 0.8 * rng.random()) * 10_000)
        rows.append((START + timedelta(hours=hour), o, h, l_, c, volume))
        close = c / 100
        closes.append(close)
        fast += (close - fast) * 2 / 21
        slow += (close - slow) * 2 / 51
    return rows, plants


def minute_bars(
    rng: random.Random, start: datetime, o: int, h: int, l_: int, c: int, volume: int
) -> list[tuple[datetime, int, int, int, int, int]]:
    """Sixty 1-minute bars inside an hour: from its open to its high and its low (in a random
    order) and on to its close, so that together they make exactly that hour."""
    first, second = sorted(rng.sample(range(1, 59), 2))
    turns = [(0, o), (first, h), (second, l_), (59, c)]
    if rng.random() < 0.5:
        turns[1], turns[2] = (first, l_), (second, h)
    path = []
    for (at, price), (until, target) in itertools.pairwise(turns):
        for minute in range(at, until):
            path.append(price + (target - price) * (minute - at) // (until - at))
    path.append(c)
    weights = [1 + rng.random() for _ in range(60)]
    shares = [int(volume * weight / sum(weights)) for weight in weights]
    shares[-1] += volume - sum(shares)
    bars, before = [], o
    for minute in range(60):
        close = path[minute + 1] if minute < 59 else c
        # The turning minutes reach the hour's high and low; others wick a little.
        wick = (h - l_) // 20
        high = min(h, max(before, close) + rng.randint(0, wick))
        low = max(l_, min(before, close) - rng.randint(0, wick))
        bars.append((start + timedelta(minutes=minute), before, high, low, close, shares[minute]))
        before = close
    return bars


def money(value: int) -> str:
    return f"{value // 100}.{value % 100:02d}"


def amount(value: int) -> str:
    return f"{value // 10_000}.{value % 10_000:04d}"


def write(path: Path, rows) -> None:
    with path.open("w", newline="\n") as file:
        file.write("timestamp,open,high,low,close,volume\n")
        for start, o, h, l_, c, volume in rows:
            stamp = start.strftime("%Y-%m-%dT%H:%M:%SZ")
            file.write(f"{stamp},{money(o)},{money(h)},{money(l_)},{money(c)},{amount(volume)}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=Path(__file__).parent, help="folder")
    parser.add_argument("--minutes", action="store_true", help="also write the 1-minute bars")
    args = parser.parse_args()
    hours, plants = hourly_bars()
    write(args.out / "demousdt-1h.csv", hours)
    print("Planted (UTC):", *plants, sep="\n  ")
    if args.minutes:
        rng = random.Random(SEED + 1)
        write(
            args.out / "demousdt-1m.csv",
            (bar for hour in hours for bar in minute_bars(rng, *hour)),
        )


if __name__ == "__main__":
    main()
