"""create trades

Revision ID: 95e6ad5d9740
Revises: 25eec0b13704
Create Date: 2026-10-13 13:04:53.424544

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "95e6ad5d9740"
down_revision: str | Sequence[str] | None = "25eec0b13704"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trades",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.String(length=5), nullable=False),
        sa.Column("status", sa.String(length=9), server_default="open", nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=19, scale=8), nullable=False),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_size", sa.Numeric(precision=19, scale=8), nullable=False),
        sa.Column(
            "entry_fee",
            sa.Numeric(precision=19, scale=8),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("exit_price", sa.Numeric(precision=19, scale=8), nullable=True),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_size", sa.Numeric(precision=19, scale=8), nullable=True),
        sa.Column(
            "exit_fee",
            sa.Numeric(precision=19, scale=8),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("stop_loss", sa.Numeric(precision=19, scale=8), nullable=True),
        sa.Column("take_profit", sa.Numeric(precision=19, scale=8), nullable=True),
        sa.Column(
            "leverage",
            sa.Numeric(precision=10, scale=2),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("pnl", sa.Numeric(precision=19, scale=8), nullable=True),
        sa.Column("pnl_pct", sa.Numeric(precision=12, scale=4), nullable=True),
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
        sa.CheckConstraint("direction IN ('long', 'short')", name=op.f("ck_trades_direction")),
        sa.CheckConstraint(
            "status <> 'closed' OR (exit_price IS NOT NULL AND exit_time IS NOT NULL"
            " AND pnl IS NOT NULL AND pnl_pct IS NOT NULL)",
            name=op.f("ck_trades_closed_trade_has_exit"),
        ),
        sa.CheckConstraint(
            "status = 'closed' OR (exit_price IS NULL AND exit_time IS NULL"
            " AND exit_size IS NULL AND pnl IS NULL AND pnl_pct IS NULL)",
            name=op.f("ck_trades_exit_fields_only_when_closed"),
        ),
        sa.CheckConstraint(
            "status IN ('open', 'closed', 'cancelled')", name=op.f("ck_trades_status")
        ),
        sa.CheckConstraint("entry_fee >= 0", name=op.f("ck_trades_entry_fee_non_negative")),
        sa.CheckConstraint("entry_price > 0", name=op.f("ck_trades_entry_price_positive")),
        sa.CheckConstraint("entry_size > 0", name=op.f("ck_trades_entry_size_positive")),
        sa.CheckConstraint("exit_fee >= 0", name=op.f("ck_trades_exit_fee_non_negative")),
        sa.CheckConstraint("exit_price > 0", name=op.f("ck_trades_exit_price_positive")),
        sa.CheckConstraint(
            "exit_size > 0 AND exit_size <= entry_size", name=op.f("ck_trades_exit_size_in_range")
        ),
        sa.CheckConstraint("exit_time >= entry_time", name=op.f("ck_trades_exit_not_before_entry")),
        sa.CheckConstraint("leverage >= 1", name=op.f("ck_trades_leverage_at_least_one")),
        sa.CheckConstraint("stop_loss > 0", name=op.f("ck_trades_stop_loss_positive")),
        sa.CheckConstraint("take_profit > 0", name=op.f("ck_trades_take_profit_positive")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_trades_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trades")),
    )
    op.create_index(
        "ix_trades_user_id_entry_time", "trades", ["user_id", "entry_time"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_trades_user_id_entry_time", table_name="trades")
    op.drop_table("trades")
