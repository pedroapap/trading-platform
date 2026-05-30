"""Trade Service - Business Logic"""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Trade, TradeAuditLog, User
from app.schemas import TradeCreate, TradeUpdate


class TradeService:
    @staticmethod
    def create_trade(
        db: Session, user_id: UUID, trade_create: TradeCreate
    ) -> Trade:
        """Create a new trade"""
        pnl = None
        pnl_pct = None

        new_trade = Trade(
            user_id=user_id,
            strategy_id=trade_create.strategy_id,
            symbol=trade_create.symbol,
            direction=trade_create.direction,
            status="open",
            entry_price=trade_create.entry_price,
            entry_time=trade_create.entry_time,
            entry_size=trade_create.entry_size,
            entry_fee=trade_create.entry_fee or Decimal(0),
            stop_loss=trade_create.stop_loss,
            take_profit=trade_create.take_profit,
            leverage=trade_create.leverage or Decimal(1.0),
            pnl=pnl,
            pnl_pct=pnl_pct,
            updated_by=user_id,
        )

        db.add(new_trade)
        db.commit()
        db.refresh(new_trade)

        TradeService._log_audit_event(
            db,
            trade_id=new_trade.id,
            event_type="entry",
            old_values=None,
            new_values={
                "symbol": new_trade.symbol,
                "direction": new_trade.direction,
                "entry_price": str(new_trade.entry_price),
                "entry_size": str(new_trade.entry_size),
            },
            changed_by=user_id,
        )

        return new_trade

    @staticmethod
    def get_trade(db: Session, user_id: UUID, trade_id: UUID) -> Optional[Trade]:
        """Get a specific trade"""
        return db.query(Trade).filter(
            Trade.id == trade_id, Trade.user_id == user_id
        ).first()

    @staticmethod
    def list_trades(
        db: Session,
        user_id: UUID,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Trade]:
        """List trades with optional filters"""
        query = db.query(Trade).filter(Trade.user_id == user_id)

        if symbol:
            query = query.filter(Trade.symbol == symbol)
        if status:
            query = query.filter(Trade.status == status)

        return query.order_by(Trade.entry_time.desc()).offset(skip).limit(limit).all()

    @staticmethod
    def update_trade(
        db: Session,
        user_id: UUID,
        trade_id: UUID,
        trade_update: TradeUpdate,
    ) -> Optional[Trade]:
        """Update a trade and log changes"""
        trade = TradeService.get_trade(db, user_id, trade_id)
        if not trade:
            return None

        old_values = {
            "exit_price": str(trade.exit_price) if trade.exit_price else None,
            "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
            "status": trade.status,
        }

        update_data = trade_update.dict(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                setattr(trade, field, value)

        if trade.exit_price and trade.entry_price:
            if trade.direction == "long":
                gross_pnl = (trade.exit_price - trade.entry_price) * trade.entry_size
            else:
                gross_pnl = (trade.entry_price - trade.exit_price) * trade.entry_size

            total_fees = (trade.entry_fee or Decimal(0)) + (trade.exit_fee or Decimal(0))
            trade.pnl = gross_pnl - total_fees
            trade.pnl_pct = (trade.pnl / (trade.entry_price * trade.entry_size)) * Decimal(100)

        if trade.status == "closed" and old_values["status"] == "open":
            event_type = "exit"
        elif trade.status == "cancelled":
            event_type = "cancel"
        else:
            event_type = "update"

        trade.updated_at = datetime.utcnow()
        trade.updated_by = user_id

        db.commit()
        db.refresh(trade)

        TradeService._log_audit_event(
            db,
            trade_id=trade.id,
            event_type=event_type,
            old_values=old_values,
            new_values={
                "exit_price": str(trade.exit_price) if trade.exit_price else None,
                "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
                "status": trade.status,
                "pnl": str(trade.pnl) if trade.pnl else None,
            },
            changed_by=user_id,
        )

        return trade

    @staticmethod
    def get_audit_log(
        db: Session, user_id: UUID, trade_id: UUID
    ) -> List[TradeAuditLog]:
        """Get audit log for a trade"""
        trade = TradeService.get_trade(db, user_id, trade_id)
        if not trade:
            return []

        return db.query(TradeAuditLog).filter(
            TradeAuditLog.trade_id == trade_id
        ).order_by(TradeAuditLog.created_at.desc()).all()

    @staticmethod
    def _log_audit_event(
        db: Session,
        trade_id: UUID,
        event_type: str,
        old_values: Optional[dict],
        new_values: Optional[dict],
        changed_by: UUID,
        change_reason: Optional[str] = None,
    ) -> TradeAuditLog:
        """Log trade changes"""
        audit_log = TradeAuditLog(
            trade_id=trade_id,
            event_type=event_type,
            old_values=old_values,
            new_values=new_values,
            changed_by=changed_by,
            change_reason=change_reason,
        )
        db.add(audit_log)
        db.commit()
        db.refresh(audit_log)
        return audit_log
