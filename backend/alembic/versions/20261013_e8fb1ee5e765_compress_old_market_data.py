"""compress old market data

Revision ID: e8fb1ee5e765
Revises: 4d1d1fedb94b
Create Date: 2026-10-13 15:42:57.158847

"""

from collections.abc import Sequence

from alembic import op

revision: str = "e8fb1ee5e765"
down_revision: str | Sequence[str] | None = "4d1d1fedb94b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Columnar compression per (symbol, timeframe) series; chunks older than 30 days are
    # compressed in the background. Inserts into compressed chunks still work.
    op.execute(
        "ALTER TABLE market_data SET (timescaledb.enable_columnstore,"
        " timescaledb.segmentby = 'symbol, timeframe', timescaledb.orderby = 'ts')"
    )
    op.execute("CALL add_columnstore_policy('market_data', after => INTERVAL '30 days')")


def downgrade() -> None:
    op.execute("CALL remove_columnstore_policy('market_data')")
    op.execute("SELECT decompress_chunk(c, true) FROM show_chunks('market_data') c")
    op.execute("ALTER TABLE market_data SET (timescaledb.enable_columnstore = false)")
