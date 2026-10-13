import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models import Strategy
from app.strategies.definition import StrategyDefinition

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str, Field(max_length=2000)]


class StrategyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Name
    description: Description | None = None
    definition: StrategyDefinition


class StrategyRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    current_version: int
    definition: StrategyDefinition
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, strategy: Strategy) -> "StrategyRead":
        return cls(
            id=strategy.id,
            name=strategy.name,
            description=strategy.description,
            current_version=strategy.current_version,
            definition=StrategyDefinition.model_validate(strategy.current.definition),
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
        )
