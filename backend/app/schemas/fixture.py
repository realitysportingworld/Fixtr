from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

from app.models.models import FixtureStatus


class FixtureResponse(BaseModel):
    id: UUID
    competition_id: UUID
    group_id: Optional[UUID]
    home_team_id: UUID
    away_team_id: UUID
    round_number: int
    scheduled_at: Optional[datetime]
    status: FixtureStatus
    knockout_round: Optional[str]
    home_score: Optional[int] = None
    away_score: Optional[int] = None

    class Config:
        from_attributes = True


class FixtureSchedule(BaseModel):
    fixture_id: UUID
    scheduled_at: datetime


class ManualFixtureCreate(BaseModel):
    home_team_id: UUID
    away_team_id: UUID
    round_number: int


class AdvanceToKnockoutRequest(BaseModel):
    teams_per_group: int = 2
