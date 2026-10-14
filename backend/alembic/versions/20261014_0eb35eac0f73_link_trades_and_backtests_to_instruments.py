"""link trades and backtests to instruments

Revision ID: 0eb35eac0f73
Revises: 0650b782e329
Create Date: 2026-10-14 13:48:06.594382

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0eb35eac0f73"
down_revision: str | Sequence[str] | None = "0650b782e329"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Every symbol in use was registered when the instruments table was created.
    op.create_foreign_key(
        op.f("fk_backtests_symbol_instruments"),
        "backtests",
        "instruments",
        ["symbol"],
        ["symbol"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_trades_symbol_instruments"),
        "trades",
        "instruments",
        ["symbol"],
        ["symbol"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_trades_symbol_instruments"), "trades", type_="foreignkey")
    op.drop_constraint(op.f("fk_backtests_symbol_instruments"), "backtests", type_="foreignkey")
