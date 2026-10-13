"""Strategies and their immutable, numbered versions."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import ConflictError, NotFoundError
from app.models import Strategy, StrategyVersion, User
from app.schemas.strategy import StrategyCreate


def _name_taken(name: str) -> ConflictError:
    return ConflictError(f"You already have a strategy named {name!r}")


def _is_duplicate_name(exc: IntegrityError) -> bool:
    return "uq_strategies_user_id" in str(exc.orig)


def create_strategy(db: Session, user: User, data: StrategyCreate) -> Strategy:
    strategy = Strategy(user_id=user.id, name=data.name, description=data.description)
    try:
        db.add(strategy)
        db.flush()
        db.add(
            StrategyVersion(
                strategy_id=strategy.id,
                version=1,
                definition=data.definition.model_dump(mode="json"),
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if _is_duplicate_name(exc):
            raise _name_taken(data.name) from None
        raise
    db.refresh(strategy)
    return strategy


def get_strategy(db: Session, user: User, strategy_id: uuid.UUID) -> Strategy:
    strategy = db.scalar(
        select(Strategy).where(Strategy.id == strategy_id, Strategy.user_id == user.id)
    )
    if strategy is None:
        raise NotFoundError("Strategy not found")
    return strategy


def list_strategies(db: Session, user: User) -> list[Strategy]:
    query = select(Strategy).where(Strategy.user_id == user.id).order_by(Strategy.name)
    return list(db.scalars(query).unique())
