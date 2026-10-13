"""add correction audit event

Revision ID: 2af3f1c8f54f
Revises: 2cfdf1878853
Create Date: 2026-10-13 15:37:26.421517

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2af3f1c8f54f"
down_revision: str | Sequence[str] | None = "2cfdf1878853"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_EVENTS = "'entry', 'update', 'exit', 'cancel'"
NEW_EVENTS = OLD_EVENTS + ", 'correction'"


def _replace_event_check(events: str, length: int) -> None:
    op.drop_constraint(op.f("ck_trade_audit_log_event_type"), "trade_audit_log", type_="check")
    # Widening a VARCHAR is metadata-only, so the append-only row trigger is not involved.
    op.alter_column("trade_audit_log", "event_type", type_=sa.String(length))
    op.create_check_constraint(
        op.f("ck_trade_audit_log_event_type"), "trade_audit_log", f"event_type IN ({events})"
    )


def upgrade() -> None:
    _replace_event_check(NEW_EVENTS, 10)


def downgrade() -> None:
    _replace_event_check(OLD_EVENTS, 6)
