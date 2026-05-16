from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.models import Competition, User
from app.schemas.competition import CompetitionCreate, CompetitionUpdate, CompetitionResponse, FREE_TIER_LIMIT
from app.services.scoring import get_default_scoring

router = APIRouter()


@router.get("/scoring-defaults")
def get_scoring_defaults():
    """Return default scoring configs for all sports."""
    from app.services.scoring import SPORT_DEFAULTS
    return SPORT_DEFAULTS


@router.post("/", response_model=CompetitionResponse, status_code=status.HTTP_201_CREATED)
def create_competition(
    payload: CompetitionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.max_participants > FREE_TIER_LIMIT and not current_user.is_premium:
        raise HTTPException(
            status_code=403,
            detail=f"Free tier is limited to {FREE_TIER_LIMIT} participants. Upgrade to premium for larger competitions.",
        )

    data = payload.model_dump()
    if data.get("scoring_config") is None:
        data["scoring_config"] = get_default_scoring(data["sport"])

    competition = Competition(
        **data,
        owner_id=current_user.id,
    )
    db.add(competition)
    db.commit()
    db.refresh(competition)
    return competition


@router.get("/", response_model=list[CompetitionResponse])
def list_competitions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Competition).filter(Competition.owner_id == current_user.id).all()


@router.get("/{competition_id}", response_model=CompetitionResponse)
def get_competition(
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
    return competition


@router.patch("/{competition_id}", response_model=CompetitionResponse)
def update_competition(
    competition_id: UUID,
    payload: CompetitionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.owner_id == current_user.id,
    ).first()
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(competition, field, value)

    db.commit()
    db.refresh(competition)
    return competition


@router.delete("/{competition_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_competition(
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

    db.delete(competition)
    db.commit()
