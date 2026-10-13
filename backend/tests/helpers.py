"""Constants and helpers shared by tests (import from here, not from conftest)."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.enums import Direction
from app.models import Trade, User

USER_EMAIL = "trader@example.com"
USER_PASSWORD = "a-long-enough-password"

ENTRY_TIME = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)


def make_trade(db: Session, user: User, **overrides: object) -> Trade:
    """Insert an open BTCUSD long (1 @ 100) directly, bypassing services."""
    values: dict[str, object] = {
        "symbol": "BTCUSD",
        "direction": Direction.LONG,
        "entry_price": Decimal("100"),
        "entry_time": ENTRY_TIME,
        "entry_size": Decimal("1"),
    }
    trade = Trade(user_id=user.id, **(values | overrides))
    db.add(trade)
    db.flush()
    db.refresh(trade)
    return trade
