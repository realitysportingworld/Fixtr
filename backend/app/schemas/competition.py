from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.models import CompetitionFormat, SportType, CompetitionStatus
from app.services import league_phase
from app.services.scoring import validate_scoring_config

FREE_TIER_LIMIT = 32
# Hard ceiling for everyone, premium included (auto-generate creates this many teams)
MAX_PARTICIPANTS = 512


class FormatConfig(BaseModel):
    # Knockout ties over two legs, decided on aggregate (the final is always one match).
    # For a LEAGUE: everyone plays everyone twice, home and away.
    two_legged: bool = False
    # LEAGUE_PHASE only; missing values get defaults scaled to max_participants
    matches_per_team: Optional[int] = Field(default=None, ge=1, le=league_phase.MAX_MATCHES_PER_TEAM)
    direct_qualifiers: Optional[int] = Field(default=None, ge=0, le=MAX_PARTICIPANTS)
    playoff_qualifiers: Optional[int] = Field(default=None, ge=0, le=MAX_PARTICIPANTS)


class CompetitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=1000)
    format: CompetitionFormat
    sport: SportType
    max_participants: int = Field(ge=2, le=MAX_PARTICIPANTS)
    num_groups: Optional[int] = None
    scoring_config: Optional[dict] = None
    format_config: Optional[FormatConfig] = None
    is_public: bool = False

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

    @model_validator(mode="after")
    def format_config_fits_format(self):
        config = self.format_config or FormatConfig()
        if self.format != CompetitionFormat.LEAGUE_PHASE:
            self.format_config = FormatConfig(two_legged=config.two_legged)
            return self

        defaults = league_phase.default_settings(self.max_participants)
        for key, value in defaults.items():
            if getattr(config, key) is None:
                setattr(config, key, value)
        # Parity is checked when fixtures are generated, against the real team count
        error = league_phase.settings_error(
            self.max_participants, config.matches_per_team, config.direct_qualifiers,
            config.playoff_qualifiers, check_parity=False,
        )
        if error:
            raise ValueError(error)
        self.format_config = config
        return self


class CompetitionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=1000)
    status: Optional[CompetitionStatus] = None
    scoring_config: Optional[dict] = None
    is_public: Optional[bool] = None

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
    format_config: Optional[dict] = None
    is_public: bool = False
    owner_id: UUID
    owner_username: Optional[str] = None
    # Owner only: the web page link, when link sharing is on
    share_url: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ShareLinkResponse(BaseModel):
    share_url: str
