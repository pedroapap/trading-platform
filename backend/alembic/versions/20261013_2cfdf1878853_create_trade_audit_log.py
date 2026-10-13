"""create trade audit log

Revision ID: 2cfdf1878853
Revises: 95e6ad5d9740
Create Date: 2026-10-13 13:06:54.452880

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2cfdf1878853"
down_revision: str | Sequence[str] | None = "95e6ad5d9740"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Rejects UPDATE, DELETE and TRUNCATE so the audit history cannot be rewritten.
APPEND_ONLY_FUNCTION = """
CREATE FUNCTION trade_audit_log_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'trade_audit_log is append-only: % is not allowed', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$
"""


def upgrade() -> None:
    op.create_table(
        "trade_audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("trade_id", sa.Uuid(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum("entry", "update", "exit", "cancel", name="event_type", native_enum=False),
            nullable=False,
        ),
        sa.Column("old_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("new_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("changed_by", sa.Uuid(), nullable=False),
        sa.Column("change_reason", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('entry', 'update', 'exit', 'cancel')",
            name=op.f("ck_trade_audit_log_event_type"),
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"], ["users.id"], name=op.f("fk_trade_audit_log_changed_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["trade_id"],
            ["trades.id"],
            name=op.f("fk_trade_audit_log_trade_id_trades"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trade_audit_log")),
    )
    op.create_index(
        op.f("ix_trade_audit_log_trade_id"), "trade_audit_log", ["trade_id"], unique=False
    )
    op.execute(APPEND_ONLY_FUNCTION)
    op.execute(
        "CREATE TRIGGER trade_audit_log_no_update_delete BEFORE UPDATE OR DELETE"
        " ON trade_audit_log FOR EACH ROW EXECUTE FUNCTION trade_audit_log_append_only()"
    )
    op.execute(
        "CREATE TRIGGER trade_audit_log_no_truncate BEFORE TRUNCATE"
        " ON trade_audit_log FOR EACH STATEMENT EXECUTE FUNCTION trade_audit_log_append_only()"
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_trade_audit_log_trade_id"), table_name="trade_audit_log")
    op.drop_table("trade_audit_log")
    op.execute("DROP FUNCTION trade_audit_log_append_only()")
