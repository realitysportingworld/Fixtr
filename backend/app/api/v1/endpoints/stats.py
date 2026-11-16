from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_viewable_competition_or_404
from app.core.security import get_current_user
from app.db.base import get_db
from app.models.models import User
from app.schemas.stats import CompetitionStats
from app.services.player_stats import competition_stats

router = APIRouter()


@router.get("/", response_model=CompetitionStats)
def get_stats(
    competition_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Top scorers, top assists and most-booked players."""
    competition = get_viewable_competition_or_404(competition_id, current_user, db)
    return competition_stats(db, competition, limit=limit)
