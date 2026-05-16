from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, model_validator


class ResultCreate(BaseModel):
    home_score: int
    away_score: int
    extra_data: Optional[dict] = None

    @model_validator(mode="after")
    def scores_non_negative(self):
        if self.home_score < 0 or self.away_score < 0:
            raise ValueError("Scores cannot be negative")
        return self


class ResultResponse(BaseModel):
    id: UUID
    fixture_id: UUID
    home_score: int
    away_score: int
    extra_data: Optional[dict]
    winner_id: Optional[UUID]
    recorded_at: datetime

    class Config:
        from_attributes = True
