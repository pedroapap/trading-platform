"""The docs' sample prices (docs/sample-data): rebuilt byte for byte by their generator,
imported with nothing rejected, and with 1-minute bars that make up exactly their hours."""

import importlib.util
import itertools
import random
import subprocess
import sys
from pathlib import Path

from app.market_data.timeframes import Timeframe
from app.services.market_data import import_bars

SAMPLE = Path(__file__).parents[2] / "docs" / "sample-data"


def generator():
    spec = importlib.util.spec_from_file_location("generate", SAMPLE / "generate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_generator_rebuilds_the_sample_file_byte_for_byte(tmp_path):
    subprocess.run(
        [sys.executable, SAMPLE / "generate.py", "--out", tmp_path], check=True, capture_output=True
    )

    assert (tmp_path / "demousdt-1h.csv").read_bytes() == (SAMPLE / "demousdt-1h.csv").read_bytes()


def test_the_sample_file_imports_with_nothing_rejected(db_session):
    with (SAMPLE / "demousdt-1h.csv").open() as file:
        summary = import_bars(db_session, file, "DEMOUSDT")

    assert (summary.timeframe, summary.inserted, summary.rejected) == (Timeframe.H1, 8760, 0)
    assert (summary.first_ts.isoformat(), summary.last_ts.isoformat()) == (
        "2025-01-01T00:00:00+00:00",
        "2025-12-31T23:00:00+00:00",
    )


def test_minute_bars_make_up_their_hour_exactly():
    generate = generator()
    hours, _ = generate.hourly_bars()
    rng = random.Random(generate.SEED + 1)

    for hour in hours[:72]:
        _, open_, high, low, close, volume = hour
        minutes = generate.minute_bars(rng, *hour)

        assert len(minutes) == 60
        assert (minutes[0][1], minutes[-1][4]) == (open_, close)
        assert (max(bar[2] for bar in minutes), min(bar[3] for bar in minutes)) == (high, low)
        assert sum(bar[5] for bar in minutes) == volume
        # Each minute opens at the close before it, and its high and low hold its open and close.
        assert all(later[1] == earlier[4] for earlier, later in itertools.pairwise(minutes))
        assert all(
            bar_low <= min(bar_open, bar_close) <= max(bar_open, bar_close) <= bar_high
            for _, bar_open, bar_high, bar_low, bar_close, _ in minutes
        )
