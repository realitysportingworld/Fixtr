from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.models import CompetitionFormat, SportType, CompetitionStatus
from app.services.scoring import validate_scoring_config

FREE_TIER_LIMIT = 32
# Hard ceiling for everyone, premium included (auto-generate creates this many teams)
MAX_PARTICIPANTS = 512


class CompetitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=1000)
    format: CompetitionFormat
    sport: SportType
    max_participants: int = Field(ge=2, le=MAX_PARTICIPANTS)
    num_groups: Optional[int] = None
    scoring_config: Optional[dict] = None

    @field_validator("scoring_config")
    @classmethod
    def scoring_config_valid(cls, v):
        return validate_scoring_config(v)

    @model_validator(mode="after")
    def groups_fit_participants(self):
        if self.format != CompetitionFormat.GROUP_KNOCKOUT:
            self.num_groups = None  # only meaningful for group knockout
            return self
        if self.num_groups is None or self.num_groups < 2:
            raise ValueError("num_groups must be at least 2 for group knockout format")
        if self.max_participants < 2 * self.num_groups:
            raise ValueError("max_participants must allow at least 2 teams per group")
        return self


class CompetitionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[CompetitionStatus] = None
    scoring_config: Optional[dict] = None

    @field_validator("scoring_config")
    @classmethod
    def scoring_config_valid(cls, v):
        return validate_scoring_config(v)


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
