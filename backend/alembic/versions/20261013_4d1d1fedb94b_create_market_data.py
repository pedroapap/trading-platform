"""create market data

Revision ID: 4d1d1fedb94b
Revises: 2af3f1c8f54f
Create Date: 2026-10-13 15:41:23.079648

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4d1d1fedb94b"
down_revision: str | Sequence[str] | None = "2af3f1c8f54f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.create_table(
        "market_data",
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column(
            "timeframe",
            sa.Enum(
                "1m", "5m", "15m", "30m", "1h", "4h", "1d", name="timeframe", native_enum=False
            ),
            nullable=False,
        ),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(precision=19, scale=8), nullable=False),
        sa.Column("high", sa.Numeric(precision=19, scale=8), nullable=False),
        sa.Column("low", sa.Numeric(precision=19, scale=8), nullable=False),
        sa.Column("close", sa.Numeric(precision=19, scale=8), nullable=False),
        sa.Column("volume", sa.Numeric(precision=28, scale=8), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "timeframe IN ('1m', '5m', '15m', '30m', '1h', '4h', '1d')",
            name=op.f("ck_market_data_timeframe"),
        ),
        sa.CheckConstraint(
            "low <= LEAST(open, close) AND high >= GREATEST(open, close)",
            name=op.f("ck_market_data_ohlc_consistent"),
        ),
        sa.CheckConstraint(
            "open > 0 AND high > 0 AND low > 0 AND close > 0",
            name=op.f("ck_market_data_prices_positive"),
        ),
        sa.CheckConstraint("volume >= 0", name=op.f("ck_market_data_volume_non_negative")),
        sa.PrimaryKeyConstraint("symbol", "timeframe", "ts", name=op.f("pk_market_data")),
    )
    # The primary key already serves time-range lookups, so skip TimescaleDB's extra ts index.
    op.execute(
        "SELECT create_hypertable('market_data', by_range('ts', INTERVAL '30 days'),"
        " create_default_indexes => false)"
    )


def downgrade() -> None:
    op.drop_table("market_data")
