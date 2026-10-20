import json
from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, model_validator

MAX_EXTRA_DATA_BYTES = 10_000
MAX_SCORE = 100_000


class ResultCreate(BaseModel):
    home_score: int = Field(le=MAX_SCORE)
    away_score: int = Field(le=MAX_SCORE)
    extra_data: Optional[dict] = None

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

    class Config:
        from_attributes = True
