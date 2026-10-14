from pydantic import BaseModel, ConfigDict

from app.schemas.common import Currency


class InstrumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    # The currency of the symbol's prices, fees and P&L; None until set when the symbol's
    # name tells nothing, as with AAPL.
    quote_currency: str | None


class InstrumentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quote_currency: Currency
