"""add detail timeframe to backtests

Revision ID: 8d8eb2e16128
Revises: 21520878d22b
Create Date: 2026-10-15 18:21:34.055848

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8d8eb2e16128"
down_revision: str | Sequence[str] | None = "21520878d22b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMEFRAMES = ("1m", "5m", "15m", "30m", "1h", "4h", "1d")


def upgrade() -> None:
    op.add_column(
        "backtests",
        sa.Column(
            "detail_timeframe",
            sa.Enum(*TIMEFRAMES, name="detail_timeframe", native_enum=False),
            nullable=True,
        ),
    )
    values = ", ".join(f"'{timeframe}'" for timeframe in TIMEFRAMES)
    op.create_check_constraint(
        op.f("ck_backtests_detail_timeframe"), "backtests", f"detail_timeframe IN ({values})"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_backtests_detail_timeframe"), "backtests", type_="check")
    op.drop_column("backtests", "detail_timeframe")
