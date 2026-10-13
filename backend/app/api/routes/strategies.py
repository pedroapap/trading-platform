import uuid
from typing import Annotated

from fastapi import APIRouter, Path, status

from app.deps import CurrentUser, DbSession
from app.models import StrategyVersion
from app.schemas.strategy import (
    StrategyCreate,
    StrategyRead,
    StrategyUpdate,
    StrategyVersionRead,
)
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


@router.get("/{strategy_id}/versions", response_model=list[StrategyVersionRead])
def list_versions(
    strategy_id: uuid.UUID, db: DbSession, user: CurrentUser
) -> list[StrategyVersion]:
    """Every saved definition, oldest first, with the fields each version changed."""
    return strategies.list_versions(db, user, strategy_id)


@router.get("/{strategy_id}/versions/{number}", response_model=StrategyVersionRead)
def get_version(
    strategy_id: uuid.UUID,
    number: Annotated[int, Path(ge=1)],
    db: DbSession,
    user: CurrentUser,
) -> StrategyVersion:
    return strategies.get_version(db, user, strategy_id, number)
