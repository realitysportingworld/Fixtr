import json
from typing import Literal, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.models import MatchEventType

MAX_EXTRA_DATA_BYTES = 10_000
MAX_SCORE = 100_000
MAX_EVENTS_PER_MATCH = 200
MAX_MINUTE = 150  # 120 plus stoppage time


class MatchEventIn(BaseModel):
    type: MatchEventType
    player_id: UUID
    # Goals only; must be a team-mate of the scorer
    assist_player_id: Optional[UUID] = None
    minute: Optional[int] = Field(default=None, ge=1, le=MAX_MINUTE)

    @model_validator(mode="after")
    def assist_fits(self):
        if self.assist_player_id is not None:
            if self.type != MatchEventType.GOAL:
                raise ValueError("Only a goal can have an assist")
            if self.assist_player_id == self.player_id:
                raise ValueError("A player can't assist their own goal")
        return self


class MatchEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fixture_id: UUID
    type: MatchEventType
    player_id: UUID
    assist_player_id: Optional[UUID]
    minute: Optional[int]


class ResultCreate(BaseModel):
    home_score: int = Field(le=MAX_SCORE)
    away_score: int = Field(le=MAX_SCORE)
    extra_data: Optional[dict] = None
    # Knockout ties that finish level (on the day, or on aggregate after the
    # second leg) are decided by penalties or another tiebreak: who won it
    tiebreak_winner: Optional[Literal["home", "away"]] = None
    # Who scored, assisted and was booked. Given = replaces the match's events
    # ([] removes them all); left out = the recorded events are kept.
    events: Optional[list[MatchEventIn]] = Field(default=None, max_length=MAX_EVENTS_PER_MATCH)

    @model_validator(mode="after")
    def scores_non_negative(self):
        if self.home_score < 0 or self.away_score < 0:
            raise ValueError("Scores cannot be negative")
        if self.extra_data is not None and len(json.dumps(self.extra_data)) > MAX_EXTRA_DATA_BYTES:
            raise ValueError("extra_data is too large")
        return self


class ResultResponse(BaseModel):
    id: UUID
    fixture_id: UUID
    home_score: int
    away_score: int
    extra_data: Optional[dict]
    winner_id: Optional[UUID]
    recorded_at: datetime

    model_config = ConfigDict(from_attributes=True)
