import uuid

from fastapi import APIRouter, status

from app.deps import CurrentUser, DbSession
from app.schemas.strategy import StrategyCreate, StrategyRead, StrategyUpdate
from app.services import strategies

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_strategy(body: StrategyCreate, db: DbSession, user: CurrentUser) -> StrategyRead:
    return StrategyRead.from_model(strategies.create_strategy(db, user, body))


@router.get("")
def list_strategies(db: DbSession, user: CurrentUser) -> list[StrategyRead]:
    return [StrategyRead.from_model(s) for s in strategies.list_strategies(db, user)]


@router.get("/{strategy_id}")
def get_strategy(strategy_id: uuid.UUID, db: DbSession, user: CurrentUser) -> StrategyRead:
    return StrategyRead.from_model(strategies.get_strategy(db, user, strategy_id))


@router.patch("/{strategy_id}")
def update_strategy(
    strategy_id: uuid.UUID, body: StrategyUpdate, db: DbSession, user: CurrentUser
) -> StrategyRead:
    """Rename, re-describe, or change the definition (which creates a new version)."""
    return StrategyRead.from_model(strategies.update_strategy(db, user, strategy_id, body))
