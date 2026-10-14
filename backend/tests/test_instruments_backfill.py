"""The migration that creates the instrument registry fills it from the symbols in use."""

from alembic import command
from sqlalchemy import Connection, text

BEFORE_INSTRUMENTS = "5bbf6863d795"


def seed(connection: Connection) -> None:
    """Trades in BTCUSDT (twice) and AAPL, bars of ETHBTC and BTCUSDT, a backtest of SOL-EUR."""
    user = connection.scalar(
        text(
            "INSERT INTO users (email, password_hash) VALUES ('old@example.com', 'x') RETURNING id"
        )
    )
    connection.execute(
        text(
            "INSERT INTO trades (user_id, symbol, direction, entry_price, entry_time, entry_size)"
            " VALUES (:user, :symbol, 'long', 1, now(), 1)"
        ),
        [{"user": user, "symbol": symbol} for symbol in ("BTCUSDT", "BTCUSDT", "AAPL")],
    )
    connection.execute(
        text(
            "INSERT INTO market_data"
            " (symbol, timeframe, ts, open, high, low, close, volume, source)"
            " VALUES (:symbol, '1d', '2026-01-01', 1, 1, 1, 1, 0, 'test')"
        ),
        [{"symbol": symbol} for symbol in ("ETHBTC", "BTCUSDT")],
    )
    strategy = connection.scalar(
        text("INSERT INTO strategies (user_id, name) VALUES (:user, 'Old') RETURNING id"),
        {"user": user},
    )
    connection.execute(
        text(
            "INSERT INTO strategy_versions (strategy_id, version, definition)"
            " VALUES (:strategy, 1, '{}')"
        ),
        {"strategy": strategy},
    )
    connection.execute(
        text(
            "INSERT INTO backtests (user_id, strategy_id, strategy_version, symbol, timeframe,"
            " initial_capital, position_size_pct, fee_pct, slippage_pct, periods_per_year)"
            " VALUES (:user, :strategy, 1, 'SOL-EUR', '1d', 1000, 100, 0, 0, 365)"
        ),
        {"user": user, "strategy": strategy},
    )


def test_symbols_in_use_are_registered_with_their_guessed_currency(engine, alembic_config):
    command.downgrade(alembic_config, BEFORE_INSTRUMENTS)
    try:
        with engine.begin() as connection:
            seed(connection)

        command.upgrade(alembic_config, "head")

        with engine.connect() as connection:
            registered = connection.execute(
                text("SELECT symbol, quote_currency FROM instruments ORDER BY symbol")
            ).all()
        assert registered == [
            ("AAPL", None),
            ("BTCUSDT", "USDT"),
            ("ETHBTC", "BTC"),
            ("SOL-EUR", "EUR"),
        ]
    finally:
        # Leave an empty database at head for the other tests.
        command.downgrade(alembic_config, "base")
        command.upgrade(alembic_config, "head")
