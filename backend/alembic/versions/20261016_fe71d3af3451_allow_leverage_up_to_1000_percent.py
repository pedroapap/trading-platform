"""allow leverage up to 1000 percent

Revision ID: fe71d3af3451
Revises: c956f8721a3e
Create Date: 2026-10-16 00:27:22.241579

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fe71d3af3451"
down_revision: str | Sequence[str] | None = "c956f8721a3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_range(limit: int, digits: int) -> None:
    op.drop_constraint(op.f("ck_backtests_position_size_in_range"), "backtests", type_="check")
    op.alter_column("backtests", "position_size_pct", type_=sa.Numeric(digits, 4))
    op.create_check_constraint(
        op.f("ck_backtests_position_size_in_range"),
        "backtests",
        f"position_size_pct > 0 AND position_size_pct <= {limit}",
    )


def upgrade() -> None:
    # 1000 needs a fourth digit before the point.
    _replace_range(1000, 8)


def downgrade() -> None:
    op.execute("UPDATE backtests SET position_size_pct = 100 WHERE position_size_pct > 100")
    _replace_range(100, 7)
