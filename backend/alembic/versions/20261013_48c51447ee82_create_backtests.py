"""create backtests

Revision ID: 48c51447ee82
Revises: fb2ebc0d96b2
Create Date: 2026-10-13 21:23:11.515171

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "48c51447ee82"
down_revision: str | Sequence[str] | None = "fb2ebc0d96b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backtests",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_version", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column(
            "timeframe",
            sa.Enum(
                "1m", "5m", "15m", "30m", "1h", "4h", "1d", name="timeframe", native_enum=False
            ),
            nullable=False,
        ),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("initial_capital", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("position_size_pct", sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column("fee_pct", sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column("slippage_pct", sa.Numeric(precision=7, scale=4), nullable=False),
        sa.Column("periods_per_year", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "completed", "failed", name="status", native_enum=False),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("bars_count", sa.Integer(), nullable=True),
        sa.Column("first_bar_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_bar_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_hash", sa.String(length=64), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("equity_curve", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status <> 'completed' OR (metrics IS NOT NULL AND equity_curve IS NOT NULL)",
            name=op.f("ck_backtests_completed_has_results"),
        ),
        sa.CheckConstraint(
            "status <> 'failed' OR error_message IS NOT NULL",
            name=op.f("ck_backtests_failed_has_reason"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name=op.f("ck_backtests_status"),
        ),
        sa.CheckConstraint(
            "timeframe IN ('1m', '5m', '15m', '30m', '1h', '4h', '1d')",
            name=op.f("ck_backtests_timeframe"),
        ),
        sa.CheckConstraint(
            "fee_pct >= 0 AND fee_pct <= 10", name=op.f("ck_backtests_fee_in_range")
        ),
        sa.CheckConstraint(
            "initial_capital > 0", name=op.f("ck_backtests_initial_capital_positive")
        ),
        sa.CheckConstraint(
            "periods_per_year BETWEEN 1 AND 366",
            name=op.f("ck_backtests_periods_per_year_in_range"),
        ),
        sa.CheckConstraint(
            "position_size_pct > 0 AND position_size_pct <= 100",
            name=op.f("ck_backtests_position_size_in_range"),
        ),
        sa.CheckConstraint(
            "slippage_pct >= 0 AND slippage_pct <= 10", name=op.f("ck_backtests_slippage_in_range")
        ),
        sa.CheckConstraint("start_ts < end_ts", name=op.f("ck_backtests_range_not_empty")),
        sa.ForeignKeyConstraint(
            ["strategy_id", "strategy_version"],
            ["strategy_versions.strategy_id", "strategy_versions.version"],
            name=op.f("fk_backtests_strategy_id_strategy_versions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_backtests_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backtests")),
    )
    op.create_index(
        "ix_backtests_user_id_created_at", "backtests", ["user_id", "created_at"], unique=False
    )
    op.create_table(
        "backtest_trades",
        sa.Column("backtest_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column(
            "direction",
            sa.Enum("long", "short", name="direction", native_enum=False),
            nullable=False,
        ),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_price", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("size", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("entry_fee", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("exit_fee", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("slippage", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("pnl", sa.Numeric(precision=28, scale=12), nullable=False),
        sa.Column("pnl_pct", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column(
            "exit_reason",
            sa.Enum(
                "signal",
                "stop_loss",
                "take_profit",
                "end_of_data",
                name="exit_reason",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.CheckConstraint(
            "direction IN ('long', 'short')", name=op.f("ck_backtest_trades_direction")
        ),
        sa.CheckConstraint(
            "exit_reason IN ('signal', 'stop_loss', 'take_profit', 'end_of_data')",
            name=op.f("ck_backtest_trades_exit_reason"),
        ),
        sa.CheckConstraint(
            "entry_price > 0 AND exit_price > 0", name=op.f("ck_backtest_trades_prices_positive")
        ),
        sa.CheckConstraint(
            "exit_time >= entry_time", name=op.f("ck_backtest_trades_exit_not_before_entry")
        ),
        sa.CheckConstraint("number >= 1", name=op.f("ck_backtest_trades_number_positive")),
        sa.CheckConstraint("size > 0", name=op.f("ck_backtest_trades_size_positive")),
        sa.ForeignKeyConstraint(
            ["backtest_id"],
            ["backtests.id"],
            name=op.f("fk_backtest_trades_backtest_id_backtests"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("backtest_id", "number", name=op.f("pk_backtest_trades")),
    )


def downgrade() -> None:
    op.drop_table("backtest_trades")
    op.drop_index("ix_backtests_user_id_created_at", table_name="backtests")
    op.drop_table("backtests")
