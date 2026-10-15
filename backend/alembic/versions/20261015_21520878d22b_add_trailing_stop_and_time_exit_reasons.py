"""add trailing stop and time exit reasons

Revision ID: 21520878d22b
Revises: 0eb35eac0f73
Create Date: 2026-10-15 18:12:03.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "21520878d22b"
down_revision: str | Sequence[str] | None = "0eb35eac0f73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_REASONS = "'signal', 'stop_loss', 'take_profit', 'end_of_data'"
NEW_REASONS = OLD_REASONS + ", 'trailing_stop', 'time_exit'"


def _replace_reason_check(reasons: str, length: int) -> None:
    op.drop_constraint(op.f("ck_backtest_trades_exit_reason"), "backtest_trades", type_="check")
    op.alter_column("backtest_trades", "exit_reason", type_=sa.String(length))
    op.create_check_constraint(
        op.f("ck_backtest_trades_exit_reason"), "backtest_trades", f"exit_reason IN ({reasons})"
    )


def upgrade() -> None:
    _replace_reason_check(NEW_REASONS, 13)


def downgrade() -> None:
    _replace_reason_check(OLD_REASONS, 11)
