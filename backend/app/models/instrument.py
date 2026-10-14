from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Instrument(TimestampMixin, Base):
    """A symbol and the currency it is quoted in, which is the currency of its prices, fees
    and P&L. Shared by all users, like market data."""

    __tablename__ = "instruments"
    __table_args__ = (
        CheckConstraint("quote_currency ~ '^[A-Z0-9]{2,10}$'", name="quote_currency_format"),
    )

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    # None until set when the symbol's name tells nothing, as with AAPL.
    quote_currency: Mapped[str | None] = mapped_column(String(10))
