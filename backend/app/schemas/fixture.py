from typing import Optional
from uuid import UUID
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.models.models import FixtureStatus


class FixtureResponse(BaseModel):
    id: UUID
    competition_id: UUID
    group_id: Optional[UUID]
    home_team_id: UUID
    away_team_id: Optional[UUID]  # null = BYE (home team auto-advances)
    round_number: int
    scheduled_at: Optional[datetime]
    status: FixtureStatus
    knockout_round: Optional[str]
    bracket_position: Optional[int] = None
    leg: Optional[int] = None  # 1 or 2 for two-legged ties, null for a single match
    is_bye: bool = False
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    winner_id: Optional[UUID] = None

    model_config = ConfigDict(from_attributes=True)

    @field_serializer("scheduled_at")
    def as_utc(self, value: Optional[datetime]):
        # Stored as naive UTC; say so, or clients read it as their local time
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


class FixtureSchedule(BaseModel):
    fixture_id: UUID
    scheduled_at: Optional[datetime]  # null clears the date

    @field_validator("scheduled_at")
    @classmethod
    def to_naive_utc(cls, value: Optional[datetime]):
        """Store UTC without tzinfo (the column has none). Naive input is taken as UTC."""
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value


class ManualFixtureCreate(BaseModel):
    home_team_id: UUID
    away_team_id: UUID
    round_number: int = Field(ge=1, le=10_000)


class AdvanceToKnockoutRequest(BaseModel):
    teams_per_group: int = Field(default=2, ge=1, le=64)
