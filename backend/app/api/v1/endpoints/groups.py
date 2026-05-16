from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.models import Competition, Group, Standing, Team, User
from app.schemas.group import GroupResponse, GroupStandingRow

router = APIRouter()


@router.get("/", response_model=list[GroupResponse])
def list_groups(
    competition_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.owner_id == current_user.id,
    ).first()
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")

    groups = (
        db.query(Group)
        .filter(Group.competition_id == competition_id)
        .order_by(Group.name)
        .all()
    )

    result = []
    for group in groups:
        teams = db.query(Team).filter(Team.group_id == group.id).all()
        standings_rows = db.query(Standing).filter(
            Standing.competition_id == competition_id,
            Standing.group_id == group.id,
        ).all()
        standings_map = {s.team_id: s for s in standings_rows}

        standing_list = []
        for team in teams:
            s = standings_map.get(team.id)
            row = GroupStandingRow(
                team_id=team.id,
                team_name=team.name,
                played=s.played if s else 0,
                wins=s.wins if s else 0,
                draws=s.draws if s else 0,
                losses=s.losses if s else 0,
                goals_for=s.goals_for if s else 0,
                goals_against=s.goals_against if s else 0,
                goal_difference=(s.goals_for - s.goals_against) if s else 0,
                points=s.points if s else 0,
            )
            standing_list.append(row)

        standing_list.sort(key=lambda x: (-x.points, -x.goal_difference, -x.goals_for, x.team_name))

        result.append(GroupResponse(id=group.id, name=group.name, standings=standing_list))

    return result
