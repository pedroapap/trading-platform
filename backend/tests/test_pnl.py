from decimal import Decimal as D

import pytest

from app.enums import Direction
from app.services.pnl import PnL, trade_pnl

LONG, SHORT = Direction.LONG, Direction.SHORT


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        # 2 @ 100 -> 110: +20 on 200 committed
        ({"direction": LONG, "exit_price": D("110")}, PnL(D("20"), D("10"))),
        ({"direction": LONG, "exit_price": D("90")}, PnL(D("-20"), D("-10"))),
        ({"direction": SHORT, "exit_price": D("90")}, PnL(D("20"), D("10"))),
        ({"direction": SHORT, "exit_price": D("110")}, PnL(D("-20"), D("-10"))),
        # both fees are deducted: 20 - 1 - 1.5
        (
            {"direction": LONG, "exit_price": D("110"), "entry_fee": D("1"), "exit_fee": D("1.5")},
            PnL(D("17.5"), D("8.75")),
        ),
        # partial exit: only 1 of 2 closed, measured against that unit's cost
        ({"direction": LONG, "exit_price": D("110"), "exit_size": D("1")}, PnL(D("10"), D("10"))),
        # 5x leverage: same profit on a fifth of the margin
        ({"direction": LONG, "exit_price": D("110"), "leverage": D("5")}, PnL(D("20"), D("50"))),
    ],
)
def test_trade_pnl(kwargs, expected):
    assert trade_pnl(entry_price=D("100"), entry_size=D("2"), **kwargs) == expected


@pytest.mark.parametrize("direction", [LONG, SHORT])
def test_breakeven_is_a_plain_zero(direction):
    result = trade_pnl(direction, D("100"), D("2"), D("100"))

    assert result.amount == D("0")
    assert result.pct == D("0")
    assert not result.amount.is_signed()
    assert not result.pct.is_signed()


def test_decimal_arithmetic_is_exact():
    # With floats, 3 * (0.3 - 0.1) is 0.6000000000000001.
    assert trade_pnl(LONG, D("0.1"), D("3"), D("0.3")).amount == D("0.6")


def test_results_are_rounded_to_column_precision():
    result = trade_pnl(LONG, D("3"), D("1"), D("3.1234567890125"))

    assert result.amount == D("0.123456789012")  # 12 decimals, half-even
    assert result.pct == D("4.1152")


def test_micro_priced_coins_keep_their_precision():
    # 1,000,000 SHIB bought at 0.000012345678 and sold at 0.000013
    result = trade_pnl(LONG, D("0.000012345678"), D("1000000"), D("0.000013"))

    assert result.amount == D("0.654322")
    assert result.pct == D("5.3000")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"entry_size": D("0")},
        {"exit_price": D("-1")},
        {"exit_size": D("3")},
        {"leverage": D("0.5")},
    ],
)
def test_invalid_inputs_are_rejected(kwargs):
    values = {"entry_price": D("100"), "entry_size": D("2"), "exit_price": D("110")} | kwargs

    with pytest.raises(ValueError):
        trade_pnl(LONG, **values)
