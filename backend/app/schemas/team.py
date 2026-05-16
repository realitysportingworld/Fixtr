from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class TeamCreate(BaseModel):
    name: str


class TeamResponse(BaseModel):
    id: UUID
    name: str
    competition_id: UUID
    group_id: Optional[UUID]

    class Config:
        from_attributes = True
