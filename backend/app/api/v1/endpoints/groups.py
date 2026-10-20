from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.models import Competition, Group, Team, User
from app.schemas.group import GroupResponse, GroupStandingRow
from app.services.standings import ranked_table

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
        rows = ranked_table(db, competition, teams, group_id=group.id)
        standing_list = [GroupStandingRow(**row) for row in rows]
        result.append(GroupResponse(id=group.id, name=group.name, standings=standing_list))

    return result
