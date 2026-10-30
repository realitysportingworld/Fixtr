from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.models import Competition, User


def get_competition_or_404(competition_id: UUID, user: User, db: Session) -> Competition:
    """A competition the user owns: required for anything that changes it."""
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.owner_id == user.id,
    ).first()
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    return competition


def get_viewable_competition_or_404(competition_id: UUID, user: User, db: Session) -> Competition:
    """A competition the user owns or one its owner made public: read-only access."""
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        or_(Competition.owner_id == user.id, Competition.is_public.is_(True)),
    ).first()
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    return competition
