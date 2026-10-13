import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.deps import CurrentUser, DbSession
from app.models import Trade
from app.schemas.trade import TradeCreate, TradeFilters, TradePage, TradeRead, TradeUpdate
from app.services import trades

router = APIRouter(prefix="/trades", tags=["trades"])


@router.post("", response_model=TradeRead, status_code=status.HTTP_201_CREATED)
def create_trade(body: TradeCreate, db: DbSession, user: CurrentUser) -> Trade:
    return trades.create_trade(db, user, body)


@router.get("")
def list_trades(
    filters: Annotated[TradeFilters, Query()], db: DbSession, user: CurrentUser
) -> TradePage:
    items, total = trades.list_trades(db, user, filters)
    return TradePage(
        items=[TradeRead.model_validate(trade) for trade in items],
        total=total,
        limit=filters.limit,
        offset=filters.offset,
    )


@router.get("/{trade_id}", response_model=TradeRead)
def get_trade(trade_id: uuid.UUID, db: DbSession, user: CurrentUser) -> Trade:
    return trades.get_trade(db, user, trade_id)


@router.patch("/{trade_id}", response_model=TradeRead)
def update_trade(trade_id: uuid.UUID, body: TradeUpdate, db: DbSession, user: CurrentUser) -> Trade:
    return trades.update_trade(db, user, trade_id, body)
