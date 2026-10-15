"""add out-of-sample split to backtests

Revision ID: d7b921158f73
Revises: 8d8eb2e16128
Create Date: 2026-10-15 18:40:17.339673

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d7b921158f73"
down_revision: str | Sequence[str] | None = "8d8eb2e16128"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "backtests", sa.Column("out_of_sample_from", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "backtests",
        sa.Column("split_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_backtests_out_of_sample_inside_range"),
        "backtests",
        "out_of_sample_from IS NULL OR ((start_ts IS NULL OR out_of_sample_from > start_ts)"
        " AND (end_ts IS NULL OR out_of_sample_from < end_ts))",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_backtests_out_of_sample_inside_range"), "backtests", type_="check")
    op.drop_column("backtests", "split_metrics")
    op.drop_column("backtests", "out_of_sample_from")
