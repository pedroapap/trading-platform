"""add end of day and margin call exit reasons

Revision ID: c956f8721a3e
Revises: d7b921158f73
Create Date: 2026-10-16 00:05:12.710214

"""

from collections.abc import Sequence

from alembic import op

revision: str = "c956f8721a3e"
down_revision: str | Sequence[str] | None = "d7b921158f73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_REASONS = "'signal', 'stop_loss', 'take_profit', 'end_of_data', 'trailing_stop', 'time_exit'"
NEW_REASONS = OLD_REASONS + ", 'end_of_day', 'margin_call'"


def _replace_reason_check(reasons: str) -> None:
    # The column stays 13 characters wide: the new reasons are shorter than trailing_stop.
    op.drop_constraint(op.f("ck_backtest_trades_exit_reason"), "backtest_trades", type_="check")
    op.create_check_constraint(
        op.f("ck_backtest_trades_exit_reason"), "backtest_trades", f"exit_reason IN ({reasons})"
    )


def upgrade() -> None:
    _replace_reason_check(NEW_REASONS)


def downgrade() -> None:
    _replace_reason_check(OLD_REASONS)
