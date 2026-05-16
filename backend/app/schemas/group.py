from uuid import UUID
from pydantic import BaseModel


class GroupStandingRow(BaseModel):
    team_id: UUID
    team_name: str
    played: int
    wins: int
    draws: int
    losses: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int

    class Config:
        from_attributes = True


class GroupResponse(BaseModel):
    id: UUID
    name: str
    standings: list[GroupStandingRow]

    class Config:
        from_attributes = True
