from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class StandingResponse(BaseModel):
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
    win_pct: float = 0.0       # wins / played
    games_behind: float = 0.0  # behind the table leader, NBA style

    class Config:
        from_attributes = True
