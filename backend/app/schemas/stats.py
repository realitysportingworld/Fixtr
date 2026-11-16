from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class PlayerStatRow(BaseModel):
    rank: int  # shared on a tie: 1, 2, 2, 4
    player_id: UUID
    player_name: str
    shirt_number: Optional[int]
    team_id: UUID
    team_name: str
    value: int  # goals, assists, or (for discipline) cards


class DisciplineRow(PlayerStatRow):
    yellow_cards: int
    red_cards: int


class CompetitionStats(BaseModel):
    supported: bool  # player stats are kept for this sport
    scorers: list[PlayerStatRow]
    assists: list[PlayerStatRow]
    discipline: list[DisciplineRow]
