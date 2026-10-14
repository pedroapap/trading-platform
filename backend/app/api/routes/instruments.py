from fastapi import APIRouter

from app.deps import CurrentUser, DbSession
from app.schemas.instrument import InstrumentRead, InstrumentUpdate
from app.services import instruments, market_data

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get("")
def list_instruments(db: DbSession, _: CurrentUser) -> list[InstrumentRead]:
    """Every symbol in use and its quote currency, alphabetically. A symbol is registered
    when it is first used, with the currency its name implies (None when it implies none)."""
    return [InstrumentRead.model_validate(i) for i in instruments.list_instruments(db)]


# `path` lets the symbol contain a slash, as in BTC/USDT.
@router.put("/{symbol:path}")
def set_quote_currency(
    symbol: str, data: InstrumentUpdate, db: DbSession, _: CurrentUser
) -> InstrumentRead:
    """Set a symbol's quote currency, registering the symbol if it is new."""
    instrument = instruments.set_quote_currency(
        db, market_data.normalize_symbol(symbol), data.quote_currency
    )
    return InstrumentRead.model_validate(instrument)
