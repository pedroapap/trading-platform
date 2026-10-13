from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.market_data.timeframes import Timeframe
from app.models.base import Base, enum_check, str_enum

Price = Numeric(19, 8)


class MarketData(Base):
    """One OHLCV bar. A TimescaleDB hypertable partitioned on `ts`; shared by all users."""

    __tablename__ = "market_data"
    __table_args__ = (
        enum_check("timeframe", Timeframe),
        CheckConstraint("open > 0 AND high > 0 AND low > 0 AND close > 0", name="prices_positive"),
        CheckConstraint(
            "low <= LEAST(open, close) AND high >= GREATEST(open, close)", name="ohlc_consistent"
        ),
        CheckConstraint("volume >= 0", name="volume_non_negative"),
    )

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    timeframe: Mapped[Timeframe] = mapped_column(str_enum(Timeframe, "timeframe"), primary_key=True)
    ts: Mapped[datetime] = mapped_column(primary_key=True)
    open: Mapped[Decimal] = mapped_column(Price)
    high: Mapped[Decimal] = mapped_column(Price)
    low: Mapped[Decimal] = mapped_column(Price)
    close: Mapped[Decimal] = mapped_column(Price)
    volume: Mapped[Decimal] = mapped_column(Numeric(28, 8))
    # File format the bar came from, e.g. "binance_klines".
    source: Mapped[str] = mapped_column(String(50))
    imported_at: Mapped[datetime] = mapped_column(server_default=func.now())
