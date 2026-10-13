"""Supported bar sizes. Bars are aligned to the Unix epoch, so daily bars start at 00:00 UTC."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum


class Timeframe(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"

    @property
    def seconds(self) -> int:
        return _SECONDS[self]

    @property
    def delta(self) -> timedelta:
        return timedelta(seconds=self.seconds)

    def is_aligned(self, ts: datetime) -> bool:
        """Whether a bar may start at `ts` (timezone-aware)."""
        since_epoch = ts - EPOCH
        return since_epoch % self.delta == timedelta(0)

    def ceil(self, ts: datetime) -> datetime:
        """The first bar start at or after `ts`."""
        remainder = (ts - EPOCH) % self.delta
        return ts if remainder == timedelta(0) else ts + (self.delta - remainder)

    def divides(self, other: "Timeframe") -> bool:
        """Whether bars of `other` can be built exactly from bars of this timeframe."""
        return other.seconds % self.seconds == 0

    @classmethod
    def from_seconds(cls, seconds: int) -> "Timeframe | None":
        return next((tf for tf in cls if tf.seconds == seconds), None)


EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

_SECONDS = {
    Timeframe.M1: 60,
    Timeframe.M5: 5 * 60,
    Timeframe.M15: 15 * 60,
    Timeframe.M30: 30 * 60,
    Timeframe.H1: 60 * 60,
    Timeframe.H4: 4 * 60 * 60,
    Timeframe.D1: 24 * 60 * 60,
}
