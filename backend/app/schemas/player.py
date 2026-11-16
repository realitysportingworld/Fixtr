from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_SHIRT_NUMBER = 999


def _clean_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = " ".join(value.split())  # trim and collapse inner whitespace
    if not value:
        raise ValueError("Player name cannot be blank")
    return value


class PlayerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    shirt_number: Optional[int] = Field(default=None, ge=0, le=MAX_SHIRT_NUMBER)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v):
        return _clean_name(v)


class PlayerUpdate(BaseModel):
    # Omitted fields are left alone; shirt_number: null removes the number
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    shirt_number: Optional[int] = Field(default=None, ge=0, le=MAX_SHIRT_NUMBER)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v):
        return _clean_name(v)


class PlayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    name: str
    shirt_number: Optional[int]
