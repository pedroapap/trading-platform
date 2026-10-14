import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Instrument
from app.services import instruments


def quote_currency(db_session, symbol: str) -> str | None:
    db_session.expire_all()
    return db_session.get(Instrument, symbol).quote_currency


def test_a_symbol_is_registered_with_its_guessed_currency(db_session):
    instruments.register(db_session, "BTCUSDT")

    assert quote_currency(db_session, "BTCUSDT") == "USDT"


def test_a_symbol_whose_name_tells_nothing_is_registered_without_a_currency(db_session):
    instruments.register(db_session, "AAPL")

    assert quote_currency(db_session, "AAPL") is None


def test_registering_a_registered_symbol_keeps_its_currency(db_session):
    db_session.add(Instrument(symbol="BTCUSDT", quote_currency="USDC"))
    db_session.flush()

    instruments.register(db_session, "BTCUSDT")

    assert quote_currency(db_session, "BTCUSDT") == "USDC"


@pytest.mark.parametrize("code", ["usd", "U", "US DOLLAR"])
def test_a_quote_currency_is_an_uppercase_code(db_session, code):
    db_session.add(Instrument(symbol="BTCUSD", quote_currency=code))

    with pytest.raises(IntegrityError, match="ck_instruments_quote_currency_format"):
        db_session.flush()
