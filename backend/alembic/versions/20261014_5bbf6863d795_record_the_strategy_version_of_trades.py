"""record the strategy version of trades

Revision ID: 5bbf6863d795
Revises: 1a12daf7045f
Create Date: 2026-10-14 12:49:28.510580

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5bbf6863d795"
down_revision: str | Sequence[str] | None = "1a12daf7045f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("strategy_version", sa.Integer(), nullable=True))
    # Trades linked before versions were recorded are taken to follow the current version.
    op.execute(
        "UPDATE trades SET strategy_version = strategies.current_version"
        " FROM strategies WHERE strategies.id = trades.strategy_id"
    )
    op.create_check_constraint(
        op.f("ck_trades_strategy_version_with_strategy"),
        "trades",
        "(strategy_id IS NULL) = (strategy_version IS NULL)",
    )
    op.create_foreign_key(
        op.f("fk_trades_strategy_id_strategy_versions"),
        "trades",
        "strategy_versions",
        ["strategy_id", "strategy_version"],
        ["strategy_id", "version"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_trades_strategy_id_strategy_versions"), "trades", type_="foreignkey"
    )
    op.drop_constraint(op.f("ck_trades_strategy_version_with_strategy"), "trades", type_="check")
    op.drop_column("trades", "strategy_version")
