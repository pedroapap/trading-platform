"""create instruments

Revision ID: 0650b782e329
Revises: 5bbf6863d795
Create Date: 2026-10-14 13:43:11.837833

"""

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0650b782e329"
down_revision: str | Sequence[str] | None = "5bbf6863d795"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# A frozen copy of app.services.instruments.guess_quote_currency, so that later changes to
# the guess don't change what this migration did.
_CRYPTO_QUOTES = {"BTC", "ETH", "BNB"}
_QUOTES = {"USDT", "USDC", "FDUSD", "BUSD", "TUSD"} | _CRYPTO_QUOTES
_QUOTES |= {"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "TRY", "BRL"}


def _guess_quote_currency(symbol: str) -> str | None:
    if "/" not in symbol:
        symbol = symbol.rpartition(":")[2]
    base, *rest = re.split(r"[/:_.-]", symbol)
    if base and rest and rest[0] in _QUOTES:
        return rest[0]
    for quote in sorted(_QUOTES, key=lambda quote: (-len(quote), quote)):
        shortest_base = 2 if quote in _CRYPTO_QUOTES else 1
        if base.endswith(quote) and len(base) - len(quote) >= shortest_base:
            return quote
    return None


def upgrade() -> None:
    instruments = op.create_table(
        "instruments",
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("quote_currency", sa.String(length=10), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "quote_currency ~ '^[A-Z0-9]{2,10}$'", name=op.f("ck_instruments_quote_currency_format")
        ),
        sa.PrimaryKeyConstraint("symbol", name=op.f("pk_instruments")),
    )
    # Every symbol already in use, with its guessed quote currency.
    symbols = op.get_bind().scalars(
        sa.text(
            "SELECT symbol FROM trades UNION SELECT symbol FROM backtests"
            " UNION SELECT DISTINCT symbol FROM market_data"
        )
    )
    rows = [
        {"symbol": symbol, "quote_currency": _guess_quote_currency(symbol)} for symbol in symbols
    ]
    if rows:
        op.bulk_insert(instruments, rows)


def downgrade() -> None:
    op.drop_table("instruments")
