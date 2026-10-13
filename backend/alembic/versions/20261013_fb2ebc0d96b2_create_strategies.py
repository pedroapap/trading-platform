"""create strategies

Revision ID: fb2ebc0d96b2
Revises: b23f1b9c0b78
Create Date: 2026-10-13 19:15:05.025630

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "fb2ebc0d96b2"
down_revision: str | Sequence[str] | None = "b23f1b9c0b78"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Generic guard for history tables: rejects UPDATE, DELETE and TRUNCATE.
APPEND_ONLY_FUNCTION = """
CREATE FUNCTION append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$
"""


def upgrade() -> None:
    op.create_table(
        "strategies",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_strategies_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategies")),
        sa.UniqueConstraint("user_id", "name", name=op.f("uq_strategies_user_id")),
    )
    op.create_table(
        "strategy_versions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changed_fields", postgresql.ARRAY(sa.String(length=50)), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_strategy_versions_version_positive")),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name=op.f("fk_strategy_versions_strategy_id_strategies"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_strategy_versions")),
        sa.UniqueConstraint(
            "strategy_id", "version", name=op.f("uq_strategy_versions_strategy_id")
        ),
    )
    op.execute(APPEND_ONLY_FUNCTION)
    op.execute(
        "CREATE TRIGGER strategy_versions_no_update_delete BEFORE UPDATE OR DELETE"
        " ON strategy_versions FOR EACH ROW EXECUTE FUNCTION append_only()"
    )
    op.execute(
        "CREATE TRIGGER strategy_versions_no_truncate BEFORE TRUNCATE"
        " ON strategy_versions FOR EACH STATEMENT EXECUTE FUNCTION append_only()"
    )
    op.create_foreign_key(
        op.f("fk_trades_strategy_id_strategies"),
        "trades",
        "strategies",
        ["strategy_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_trades_strategy_id_strategies"), "trades", type_="foreignkey")
    op.drop_table("strategy_versions")
    op.execute("DROP FUNCTION append_only()")
    op.drop_table("strategies")
