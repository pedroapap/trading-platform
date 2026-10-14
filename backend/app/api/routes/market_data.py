import io
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status

from app.config import get_settings
from app.deps import CurrentUser, DbSession
from app.market_data.timeframes import Timeframe
from app.schemas.market_data import (
    BarQuery,
    BarRead,
    BarsResponse,
    CoverageRead,
    ImportResult,
)
from app.services import market_data

router = APIRouter(prefix="/market-data", tags=["market data"])


@router.post("/import")
def import_file(
    db: DbSession,
    _: CurrentUser,
    file: Annotated[UploadFile, File(description="CSV price file")],
    symbol: Annotated[str, Form(description="Symbol the bars belong to, e.g. BTCUSDT")],
    timeframe: Annotated[
        Timeframe | None, Form(description="Bar size; inferred if omitted")
    ] = None,
    format: Annotated[str | None, Form(description="File format; detected if omitted")] = None,
) -> ImportResult:
    """Import OHLCV bars. Existing bars are kept; invalid rows are skipped and reported."""
    limit_mb = get_settings().max_upload_mb
    if file.size is not None and file.size > limit_mb * 1024 * 1024:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, f"The file is larger than {limit_mb} MB"
        )
    # Starlette has already spooled the upload to a seekable temp file; read it as text.
    stream = io.TextIOWrapper(file.file, encoding="utf-8-sig", newline="")
    summary = market_data.import_bars(db, stream, symbol, timeframe, format)
    return ImportResult.model_validate(summary)


# `path` lets the symbol contain a slash, as in BTC/USDT.
@router.get("/{symbol:path}/bars")
def get_bars(
    symbol: str, query: Annotated[BarQuery, Query()], db: DbSession, _: CurrentUser
) -> BarsResponse:
    result = market_data.get_bars(db, symbol, query)
    return BarsResponse(
        symbol=market_data.normalize_symbol(symbol),
        timeframe=query.timeframe,
        aggregated_from=result.aggregated_from,
        bars=[BarRead.model_validate(bar) for bar in result.bars],
    )


@router.get("/symbols")
def list_coverage(db: DbSession, _: CurrentUser) -> list[CoverageRead]:
    """What is stored: one entry per symbol and timeframe, with its time range and bar count."""
    return [
        CoverageRead.model_validate(entry, from_attributes=True)
        for entry in market_data.coverage(db)
    ]
