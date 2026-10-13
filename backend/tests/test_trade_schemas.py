import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.enums import Direction, TradeStatus
from app.schemas.trade import TradeClose, TradeCreate, TradeRead, TradeUpdate

VALID = {
    "symbol": " btcusd ",
    "direction": "long",
    "entry_price": "45000.5",
    "entry_time": "2026-01-05T14:30:00Z",
    "entry_size": 0.25,
}


def test_create_normalizes_and_fills_defaults():
    trade = TradeCreate.model_validate(VALID)

    assert trade.symbol == "BTCUSD"
    assert trade.direction is Direction.LONG
    assert trade.entry_price == Decimal("45000.5")
    assert trade.entry_size == Decimal("0.25")
    assert trade.entry_fee == Decimal("0")
    assert trade.leverage == Decimal("1")


@pytest.mark.parametrize(
    "override",
    [
        {"entry_price": "0"},
        {"entry_size": "-1"},
        {"entry_fee": "-0.5"},
        {"entry_price": "1.123456789"},  # more decimals than the column stores
        {"leverage": "0.5"},
        {"direction": "sideways"},
        {"symbol": "BTC USD"},
        {"symbol": "X" * 21},
        {"entry_time": "2026-01-05T14:30:00"},  # naive: timezone required
        {"exit_price": "50000"},  # exits only via /close
    ],
)
def test_create_rejects_invalid_input(override):
    with pytest.raises(ValidationError):
        TradeCreate.model_validate(VALID | override)


def test_update_reports_only_the_fields_sent():
    update = TradeUpdate.model_validate({"stop_loss": "44000", "take_profit": None})

    assert update.changes() == {"stop_loss": Decimal("44000"), "take_profit": None}


@pytest.mark.parametrize(
    "payload",
    [
        {"entry_price": None},  # required fields cannot be cleared
        {"exit_price": "50000"},
        {"status": "closed"},
    ],
)
def test_update_rejects_invalid_changes(payload):
    with pytest.raises(ValidationError):
        TradeUpdate.model_validate(payload)


def test_close_defaults_and_requirements():
    close = TradeClose.model_validate({"exit_price": "46000", "exit_time": "2026-01-06T10:00Z"})

    assert close.exit_size is None
    assert close.exit_fee == Decimal("0")
    with pytest.raises(ValidationError):
        TradeClose.model_validate({"exit_price": "46000"})


def test_read_serializes_decimals_as_exact_strings():
    now = datetime(2026, 1, 5, tzinfo=UTC)
    trade = TradeRead(
        id=uuid.uuid4(),
        strategy_id=None,
        symbol="BTCUSD",
        direction=Direction.LONG,
        status=TradeStatus.CLOSED,
        entry_price=Decimal("45000.00000000"),
        entry_time=now,
        entry_size=Decimal("0.10000000"),
        entry_fee=Decimal("0E-8"),
        exit_price=Decimal("46000.12345678"),
        exit_time=now,
        exit_size=None,
        exit_fee=Decimal("0"),
        stop_loss=None,
        take_profit=None,
        leverage=Decimal("1.00"),
        pnl=Decimal("100.01234568"),
        pnl_pct=Decimal("2.2225"),
        created_at=now,
        updated_at=now,
    )

    body = trade.model_dump(mode="json")

    assert body["entry_price"] == "45000"
    assert body["entry_size"] == "0.1"
    assert body["entry_fee"] == "0"
    assert body["exit_price"] == "46000.12345678"
    assert body["leverage"] == "1"
    assert body["exit_size"] is None
