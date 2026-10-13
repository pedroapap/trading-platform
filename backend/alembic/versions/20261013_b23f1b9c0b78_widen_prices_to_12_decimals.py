"""widen prices to 12 decimals

Revision ID: b23f1b9c0b78
Revises: e8fb1ee5e765
Create Date: 2026-10-13 19:11:48.215679

"""

from collections.abc import Sequence

from alembic import op

revision: str = "b23f1b9c0b78"
down_revision: str | Sequence[str] | None = "e8fb1ee5e765"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


MARKET_DATA_COLUMNS = ("open", "high", "low", "close")
TRADE_COLUMNS = (
    "entry_price",
    "entry_size",
    "entry_fee",
    "exit_price",
    "exit_size",
    "exit_fee",
    "stop_loss",
    "take_profit",
    "pnl",
)


def _alter(table: str, columns: tuple[str, ...], type_: str) -> None:
    # One statement per table, so each table is rewritten once.
    clauses = ", ".join(f"ALTER COLUMN {column} TYPE {type_}" for column in columns)
    op.execute(f"ALTER TABLE {table} {clauses}")


def _set_price_type(type_: str) -> None:
    # TimescaleDB cannot change column types while compression is enabled, so pause it.
    op.execute("CALL remove_columnstore_policy('market_data')")
    op.execute("SELECT decompress_chunk(c, true) FROM show_chunks('market_data') c")
    op.execute("ALTER TABLE market_data SET (timescaledb.enable_columnstore = false)")
    _alter("market_data", MARKET_DATA_COLUMNS, type_)
    _alter("trades", TRADE_COLUMNS, type_)
    op.execute(
        "ALTER TABLE market_data SET (timescaledb.enable_columnstore,"
        " timescaledb.segmentby = 'symbol, timeframe', timescaledb.orderby = 'ts')"
    )
    op.execute("CALL add_columnstore_policy('market_data', after => INTERVAL '30 days')")


def upgrade() -> None:
    _set_price_type("NUMERIC(28, 12)")


def downgrade() -> None:
    # Rounds values back to 8 decimals.
    _set_price_type("NUMERIC(19, 8)")
