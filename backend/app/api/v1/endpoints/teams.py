from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.models import Competition, CompetitionStatus, Team, User
from app.schemas.team import TeamCreate, TeamResponse

router = APIRouter()


def get_competition_or_404(competition_id: UUID, user: User, db: Session) -> Competition:
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.owner_id == user.id,
    ).first()
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    return competition


@router.post("/", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
def add_team(
    competition_id: UUID,
    payload: TeamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    competition = get_competition_or_404(competition_id, current_user, db)

    if competition.status != CompetitionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Cannot add teams to an active or completed competition")

    current_count = db.query(Team).filter(Team.competition_id == competition_id).count()
    if current_count >= competition.max_participants:
        raise HTTPException(
            status_code=400,
            detail=f"Competition is full ({competition.max_participants} teams max)",
        )

    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Team name cannot be blank")
    if db.query(Team).filter(Team.competition_id == competition_id, Team.name == name).first():
        raise HTTPException(status_code=400, detail=f"A team named '{name}' already exists in this competition")

    team = Team(name=name, competition_id=competition_id)
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


@router.get("/", response_model=list[TeamResponse])
def list_teams(
    competition_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_competition_or_404(competition_id, current_user, db)
    return db.query(Team).filter(Team.competition_id == competition_id).all()


@router.post("/generate", response_model=list[TeamResponse], status_code=status.HTTP_201_CREATED)
def auto_generate_teams(
    competition_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fill remaining team slots with placeholder names (Team 1, Team 2, ...)."""
    competition = get_competition_or_404(competition_id, current_user, db)

    if competition.status != CompetitionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Cannot add teams to an active or completed competition")

    existing = db.query(Team).filter(Team.competition_id == competition_id).all()
    existing_names = {t.name for t in existing}
    slots_remaining = competition.max_participants - len(existing)

    if slots_remaining <= 0:
        raise HTTPException(status_code=400, detail="Competition is already full")

    new_teams = []
    counter = 1
    while len(new_teams) < slots_remaining:
        name = f"Team {counter}"
        if name not in existing_names:
            team = Team(name=name, competition_id=competition_id)
            db.add(team)
            new_teams.append(team)
        counter += 1

    db.commit()
    for t in new_teams:
        db.refresh(t)

    return new_teams


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_team(
    competition_id: UUID,
    team_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    competition = get_competition_or_404(competition_id, current_user, db)

    if competition.status != CompetitionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Cannot remove teams from an active or completed competition")

    team = db.query(Team).filter(Team.id == team_id, Team.competition_id == competition_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")

    db.delete(team)
    db.commit()
