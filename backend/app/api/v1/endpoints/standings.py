from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.models import Competition, Standing, Team, User
from app.schemas.standing import StandingResponse

router = APIRouter()


@router.get("/", response_model=list[StandingResponse])
def get_standings(
    competition_id: UUID,
    group_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.owner_id == current_user.id,
    ).first()
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")

    # All teams in the competition
    all_teams = db.query(Team).filter(Team.competition_id == competition_id).all()
    team_map = {t.id: t for t in all_teams}

    # Existing standing rows
    standing_query = db.query(Standing).filter(Standing.competition_id == competition_id)
    if group_id:
        standing_query = standing_query.filter(Standing.group_id == group_id)
    standings_map = {s.team_id: s for s in standing_query.all()}

    result = []
    for team in all_teams:
        s = standings_map.get(team.id)
        if s:
            result.append(StandingResponse(
                team_id=team.id,
                team_name=team.name,
                played=s.played,
                wins=s.wins,
                draws=s.draws,
                losses=s.losses,
                goals_for=s.goals_for,
                goals_against=s.goals_against,
                goal_difference=s.goals_for - s.goals_against,
                points=s.points,
            ))
        else:
            # Team has no results yet — show with zeros
            result.append(StandingResponse(
                team_id=team.id,
                team_name=team.name,
                played=0, wins=0, draws=0, losses=0,
                goals_for=0, goals_against=0,
                goal_difference=0, points=0,
            ))

    # Sort: by points desc, goal difference desc, then alphabetically for ties
    result.sort(key=lambda x: (-x.points, -x.goal_difference, -x.goals_for, x.team_name))

    return result
