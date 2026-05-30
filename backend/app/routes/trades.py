"""Trade Routes - CRUD API"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import TradeCreate, TradeUpdate, TradeResponse
from app.services.trade_service import TradeService

router = APIRouter()


def get_current_user_id(request: Request) -> UUID:
    """Extract user_id from request state"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return UUID(user_id)


@router.post("/", response_model=TradeResponse, status_code=status.HTTP_201_CREATED)
def create_trade(
    trade_create: TradeCreate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Create a new trade"""
    trade = TradeService.create_trade(db, user_id, trade_create)
    return trade


@router.get("/", response_model=List[TradeResponse])
def list_trades(
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
    symbol: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    """List all trades for user"""
    trades = TradeService.list_trades(
        db, user_id, symbol=symbol, status=status, skip=skip, limit=limit
    )
    return trades


@router.get("/{trade_id}", response_model=TradeResponse)
def get_trade(
    trade_id: str,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Get a specific trade"""
    try:
        trade_uuid = UUID(trade_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid trade ID")

    trade = TradeService.get_trade(db, user_id, trade_uuid)
    if not trade:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")

    return trade


@router.patch("/{trade_id}", response_model=TradeResponse)
def update_trade(
    trade_id: str,
    trade_update: TradeUpdate,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Update a trade"""
    try:
        trade_uuid = UUID(trade_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid trade ID")

    trade = TradeService.update_trade(db, user_id, trade_uuid, trade_update)
    if not trade:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")

    return trade


@router.get("/{trade_id}/audit-log")
def get_trade_audit_log(
    trade_id: str,
    db: Session = Depends(get_db),
    user_id: UUID = Depends(get_current_user_id),
):
    """Get immutable audit log for a trade"""
    try:
        trade_uuid = UUID(trade_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid trade ID")

    audit_logs = TradeService.get_audit_log(db, user_id, trade_uuid)
    if not audit_logs:
        trade = TradeService.get_trade(db, user_id, trade_uuid)
        if not trade:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade not found")

    return {
        "trade_id": str(trade_uuid),
        "events": [
            {
                "id": str(log.id),
                "event_type": log.event_type,
                "old_values": log.old_values,
                "new_values": log.new_values,
                "changed_by": str(log.changed_by),
                "change_reason": log.change_reason,
                "created_at": log.created_at.isoformat(),
            }
            for log in audit_logs
        ],
    }
