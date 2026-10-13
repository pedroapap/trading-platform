"""Reusable field types for API schemas."""

from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, Field, PlainSerializer, StringConstraints


def _plain_decimal(value: Decimal) -> str:
    # Exact and readable: 45000.00000000 -> "45000", 0.10000000 -> "0.1" (never a float).
    return format(value.normalize(), "f")


DecimalOut = Annotated[Decimal, PlainSerializer(_plain_decimal, return_type=str, when_used="json")]

# Inputs match the NUMERIC(19, 8) columns, so values are never silently rounded.
Price = Annotated[Decimal, Field(gt=0, max_digits=19, decimal_places=8)]
Fee = Annotated[Decimal, Field(ge=0, max_digits=19, decimal_places=8)]
Leverage = Annotated[Decimal, Field(ge=1, max_digits=10, decimal_places=2)]


def _normalize_symbol(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


# Normalized before validating, since StringConstraints checks the pattern first.
Symbol = Annotated[
    str,
    BeforeValidator(_normalize_symbol),
    StringConstraints(min_length=1, max_length=20, pattern=r"^[A-Z0-9][A-Z0-9._:/-]*$"),
]
