"""Instruments: the currency each symbol is quoted in, which is the currency of its prices,
fees and P&L. A symbol is registered the first time it is used, with the currency its name
implies; a currency it doesn't imply, or a wrong guess, is set by hand."""

import re

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import Instrument

STABLECOINS = frozenset({"USDT", "USDC", "FDUSD", "BUSD", "TUSD"})
FIAT = frozenset({"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "TRY", "BRL"})
# A symbol needs two or more characters before these to be read as a pair, so that tokens
# and funds named after them (WBTC, GBTC, WETH) are not taken for one.
CRYPTO_QUOTES = frozenset({"BTC", "ETH", "BNB"})
QUOTE_CURRENCIES = STABLECOINS | FIAT | CRYPTO_QUOTES

# Longest first, so that BTCFDUSD is quoted in FDUSD rather than USD.
_LONGEST_FIRST = sorted(QUOTE_CURRENCIES, key=lambda quote: (-len(quote), quote))
_SEPARATOR = re.compile(r"[/:_.-]")


def guess_quote_currency(symbol: str) -> str | None:
    """The quote currency a normalized symbol's name implies, or None when it tells nothing.

    A known currency after a separator is the quote (BTC/USDT, BTC-USD, ETH_BTC, ccxt's
    BTC/USDT:USDT); otherwise it is the longest known currency the symbol ends with (BTCUSDT,
    ETHBTC, EURUSD). An exchange prefix (BINANCE:BTCUSDT) and a derivative suffix (BTCUSDT.P,
    BTCUSD_PERP) are ignored. AAPL tells nothing, and neither does USDT on its own.
    """
    if "/" not in symbol:
        symbol = symbol.rpartition(":")[2]
    base, *rest = _SEPARATOR.split(symbol)
    if base and rest and rest[0] in QUOTE_CURRENCIES:
        return rest[0]
    for quote in _LONGEST_FIRST:
        shortest_base = 2 if quote in CRYPTO_QUOTES else 1
        if base.endswith(quote) and len(base) - len(quote) >= shortest_base:
            return quote
    return None


def register(db: Session, symbol: str) -> None:
    """Add a normalized symbol to the registry with its guessed quote currency, in the
    caller's transaction; a registered symbol is left as it is."""
    db.execute(
        insert(Instrument)
        .values(symbol=symbol, quote_currency=guess_quote_currency(symbol))
        .on_conflict_do_nothing(index_elements=[Instrument.symbol])
    )


def list_instruments(db: Session) -> list[Instrument]:
    """Every registered symbol, alphabetically."""
    return list(db.scalars(select(Instrument).order_by(Instrument.symbol)))


def set_quote_currency(db: Session, symbol: str, currency: str) -> Instrument:
    """Set a normalized symbol's quote currency, registering the symbol if it is new."""
    upsert = insert(Instrument).values(symbol=symbol, quote_currency=currency)
    upsert = upsert.on_conflict_do_update(
        index_elements=[Instrument.symbol],
        set_={"quote_currency": currency, "updated_at": func.now()},
    )
    try:
        instrument = db.scalars(
            upsert.returning(Instrument), execution_options={"populate_existing": True}
        ).one()
        db.commit()
    except Exception:
        db.rollback()
        raise
    return instrument
