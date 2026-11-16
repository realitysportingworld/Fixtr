from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TeamResponse(BaseModel):
    id: UUID
    name: str
    competition_id: UUID
    group_id: Optional[UUID]

    model_config = ConfigDict(from_attributes=True)
