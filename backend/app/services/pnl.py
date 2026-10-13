"""Profit and loss of a closed trade. Pure functions, exact Decimal arithmetic."""

from dataclasses import dataclass
from decimal import Decimal, localcontext

from app.enums import Direction

AMOUNT_STEP = Decimal("0.00000001")  # NUMERIC(19, 8)
PERCENT_STEP = Decimal("0.0001")  # NUMERIC(12, 4)
ZERO = Decimal(0)


@dataclass(frozen=True)
class PnL:
    amount: Decimal
    # Return on the margin committed (notional / leverage), in percent.
    pct: Decimal


def trade_pnl(
    direction: Direction,
    entry_price: Decimal,
    entry_size: Decimal,
    exit_price: Decimal,
    exit_size: Decimal | None = None,
    entry_fee: Decimal = ZERO,
    exit_fee: Decimal = ZERO,
    leverage: Decimal = Decimal(1),
) -> PnL:
    """P&L on the exited quantity (`exit_size`, defaulting to the whole position), net of fees."""
    size = entry_size if exit_size is None else exit_size
    if min(entry_price, exit_price, entry_size, size) <= 0:
        raise ValueError("prices and sizes must be positive")
    if size > entry_size:
        raise ValueError("exit size cannot exceed entry size")
    if leverage < 1:
        raise ValueError("leverage must be at least 1")

    with localcontext() as ctx:
        ctx.prec = 50  # well beyond NUMERIC(19, 8) products, so nothing rounds early
        sign = 1 if direction == Direction.LONG else -1
        amount = (exit_price - entry_price) * size * sign - entry_fee - exit_fee
        margin = entry_price * size / leverage
        pct = amount / margin * 100
        # `+ ZERO` turns a negative zero (short at breakeven) into a plain zero.
        return PnL(amount.quantize(AMOUNT_STEP) + ZERO, pct.quantize(PERCENT_STEP) + ZERO)
