from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_viewable_competition_or_404
from app.core.security import get_current_user
from app.db.base import get_db
from app.models.models import Team, User
from app.schemas.standing import StandingResponse
from app.services.standings import ranked_table

router = APIRouter()


@router.get("/", response_model=list[StandingResponse])
def get_standings(
    competition_id: UUID,
    group_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    competition = get_viewable_competition_or_404(competition_id, current_user, db)

    teams_query = db.query(Team).filter(Team.competition_id == competition_id)
    if group_id:
        teams_query = teams_query.filter(Team.group_id == group_id)

    rows = ranked_table(db, competition, teams_query.all(), group_id=group_id)
    return [StandingResponse(**row) for row in rows]
