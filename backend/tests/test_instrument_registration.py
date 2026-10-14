"""Storing a trade, bars or a backtest registers its symbol with the guessed quote currency."""

from sqlalchemy import delete, select

from app.models import Instrument
from app.schemas.backtest import BacktestCreate
from app.schemas.trade import TradeCorrection, TradeCreate, TradeUpdate
from app.services import backtests, trades
from tests.helpers import make_closed_trade, make_strategy, random_bars, store_bars


def registered(db) -> dict[str, str | None]:
    return dict(db.execute(select(Instrument.symbol, Instrument.quote_currency)).all())


def new_trade(symbol: str) -> TradeCreate:
    return TradeCreate(
        symbol=symbol,
        direction="long",
        entry_price="100",
        entry_time="2026-01-05T14:30:00Z",
        entry_size="1",
    )


def test_a_trade_registers_its_symbol(db_session, user):
    trades.create_trade(db_session, user, new_trade("ethbtc"))

    assert registered(db_session) == {"ETHBTC": "BTC"}


def test_a_registered_currency_is_kept(db_session, user):
    db_session.add(Instrument(symbol="BTCUSDT", quote_currency="USDC"))
    db_session.flush()

    trades.create_trade(db_session, user, new_trade("BTCUSDT"))

    assert registered(db_session) == {"BTCUSDT": "USDC"}


def test_a_trade_moved_to_another_symbol_registers_it(db_session, user):
    trade = trades.create_trade(db_session, user, new_trade("BTCUSDT"))

    trades.update_trade(db_session, user, trade.id, TradeUpdate(symbol="soleur"))

    assert registered(db_session) == {"BTCUSDT": "USDT", "SOLEUR": "EUR"}


def test_a_trade_corrected_to_another_symbol_registers_it(db_session, user):
    trade = make_closed_trade(db_session, user, "5")

    trades.correct_trade(
        db_session, user, trade.id, TradeCorrection(symbol="ethbtc", reason="Wrong pair")
    )

    assert registered(db_session) == {"ETHBTC": "BTC"}


def test_imported_bars_register_their_symbol(db_session):
    store_bars(db_session, random_bars(10), symbol="ETHUSDT")

    assert registered(db_session) == {"ETHUSDT": "USDT"}


def test_a_backtest_registers_its_symbol(db_session, user):
    store_bars(db_session, random_bars(10))
    db_session.execute(delete(Instrument))
    strategy = make_strategy(db_session, user)

    backtests.create_backtest(
        db_session,
        user,
        BacktestCreate(strategy_id=strategy.id, symbol="BTCUSD", timeframe="1m"),
    )

    assert registered(db_session) == {"BTCUSD": "USD"}
