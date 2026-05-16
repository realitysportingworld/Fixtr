from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, field_validator

from app.models.models import CompetitionFormat, SportType, CompetitionStatus

FREE_TIER_LIMIT = 32


class CompetitionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    format: CompetitionFormat
    sport: SportType
    max_participants: int
    num_groups: Optional[int] = None
    scoring_config: Optional[dict] = None

    @field_validator("max_participants")
    @classmethod
    def must_be_positive_and_even(cls, v):
        if v < 2:
            raise ValueError("must have at least 2 participants")
        if v % 2 != 0:
            raise ValueError("must be an even number")
        return v


class CompetitionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[CompetitionStatus] = None
    scoring_config: Optional[dict] = None


class CompetitionResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    format: CompetitionFormat
    sport: SportType
    status: CompetitionStatus
    max_participants: int
    num_groups: Optional[int]
    scoring_config: Optional[dict]
    owner_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True
