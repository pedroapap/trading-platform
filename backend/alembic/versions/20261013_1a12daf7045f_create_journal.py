"""create journal

Revision ID: 1a12daf7045f
Revises: 48c51447ee82
Create Date: 2026-10-13 21:48:04.941502

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "1a12daf7045f"
down_revision: str | Sequence[str] | None = "48c51447ee82"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "journal_entries",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("trade_id", sa.Uuid(), nullable=True),
        sa.Column(
            "entry_type",
            sa.Enum("pre_trade", "post_trade", "note", name="entry_type", native_enum=False),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("thesis", sa.Text(), nullable=True),
        sa.Column("market_context", sa.Text(), nullable=True),
        sa.Column("risk_assessment", sa.Text(), nullable=True),
        sa.Column("lessons", sa.Text(), nullable=True),
        sa.Column(
            "emotion",
            sa.Enum(
                "calm",
                "confident",
                "excited",
                "greedy",
                "fomo",
                "fearful",
                "frustrated",
                "impatient",
                "uncertain",
                name="emotion",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String(length=50)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("draft", "published", name="status", native_enum=False),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("current_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'published') = (current_version >= 1)",
            name=op.f("ck_journal_entries_versions_when_published"),
        ),
        sa.CheckConstraint(
            "(status = 'published') = (published_at IS NOT NULL)",
            name=op.f("ck_journal_entries_published_at_when_published"),
        ),
        sa.CheckConstraint(
            "emotion IN ('calm', 'confident', 'excited', 'greedy', 'fomo', 'fearful',"
            " 'frustrated', 'impatient', 'uncertain')",
            name=op.f("ck_journal_entries_emotion"),
        ),
        sa.CheckConstraint(
            "entry_type IN ('pre_trade', 'post_trade', 'note')",
            name=op.f("ck_journal_entries_entry_type"),
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'published')", name=op.f("ck_journal_entries_status")
        ),
        sa.CheckConstraint(
            "current_version >= 0", name=op.f("ck_journal_entries_version_not_negative")
        ),
        sa.ForeignKeyConstraint(
            ["trade_id"],
            ["trades.id"],
            name=op.f("fk_journal_entries_trade_id_trades"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_journal_entries_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_entries")),
    )
    op.create_index(
        "ix_journal_entries_user_id_created_at",
        "journal_entries",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "journal_entry_versions",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changed_fields", postgresql.ARRAY(sa.String(length=50)), nullable=True),
        sa.Column("edit_reason", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("clock_timestamp()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(version = 1) = (edit_reason IS NULL)",
            name=op.f("ck_journal_entry_versions_edits_have_a_reason"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_journal_entry_versions_version_positive")),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["journal_entries.id"],
            name=op.f("fk_journal_entry_versions_entry_id_journal_entries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_journal_entry_versions")),
        sa.UniqueConstraint("entry_id", "version", name=op.f("uq_journal_entry_versions_entry_id")),
    )
    # append_only() comes from the strategies migration.
    op.execute(
        "CREATE TRIGGER journal_entry_versions_no_update_delete BEFORE UPDATE OR DELETE"
        " ON journal_entry_versions FOR EACH ROW EXECUTE FUNCTION append_only()"
    )
    op.execute(
        "CREATE TRIGGER journal_entry_versions_no_truncate BEFORE TRUNCATE"
        " ON journal_entry_versions FOR EACH STATEMENT EXECUTE FUNCTION append_only()"
    )


def downgrade() -> None:
    op.drop_table("journal_entry_versions")
    op.drop_index("ix_journal_entries_user_id_created_at", table_name="journal_entries")
    op.drop_table("journal_entries")
