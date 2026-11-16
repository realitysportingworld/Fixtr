"""
Team squads. Players can be added and edited at any point in the season
(squads change), but a player with goals, assists or cards recorded can't be
removed until those are taken off the matches.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_competition_or_404, get_viewable_competition_or_404
from app.core.security import get_current_user
from app.db.base import get_db
from app.models.models import CompetitionStatus, MatchEvent, Player, Team, User
from app.schemas.player import PlayerCreate, PlayerResponse, PlayerUpdate

router = APIRouter()

MAX_PLAYERS_PER_TEAM = 60


def _team_or_404(db: Session, competition_id: UUID, team_id: UUID) -> Team:
    team = db.query(Team).filter(Team.id == team_id, Team.competition_id == competition_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


def _player_or_404(db: Session, team_id: UUID, player_id: UUID) -> Player:
    player = db.query(Player).filter(Player.id == player_id, Player.team_id == team_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


def _editable(competition) -> None:
    if competition.status == CompetitionStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Competition is cancelled")


def _check_unique(db: Session, team_id: UUID, name: str | None, number: int | None, exclude: UUID | None = None):
    query = db.query(Player).filter(Player.team_id == team_id)
    if exclude:
        query = query.filter(Player.id != exclude)
    if name is not None and query.filter(func.lower(Player.name) == name.lower()).first():
        raise HTTPException(status_code=400, detail=f"'{name}' is already in this squad")
    if number is not None and query.filter(Player.shirt_number == number).first():
        raise HTTPException(status_code=400, detail=f"Number {number} is already taken in this squad")


def _commit(db: Session) -> None:
    """Commit, turning a unique-constraint race (two identical adds at once) into a 400."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="That name or number is already in this squad")


@router.get("/", response_model=list[PlayerResponse])
def list_players(
    competition_id: UUID,
    team_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_viewable_competition_or_404(competition_id, current_user, db)
    _team_or_404(db, competition_id, team_id)
    return (
        db.query(Player)
        .filter(Player.team_id == team_id)
        .order_by(Player.shirt_number.is_(None), Player.shirt_number, Player.name)
        .all()
    )


@router.post("/", response_model=PlayerResponse, status_code=status.HTTP_201_CREATED)
def add_player(
    competition_id: UUID,
    team_id: UUID,
    payload: PlayerCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    competition = get_competition_or_404(competition_id, current_user, db)
    _editable(competition)
    _team_or_404(db, competition_id, team_id)

    if db.query(Player).filter(Player.team_id == team_id).count() >= MAX_PLAYERS_PER_TEAM:
        raise HTTPException(status_code=400, detail=f"A squad can have at most {MAX_PLAYERS_PER_TEAM} players")
    _check_unique(db, team_id, payload.name, payload.shirt_number)

    player = Player(team_id=team_id, name=payload.name, shirt_number=payload.shirt_number)
    db.add(player)
    _commit(db)
    db.refresh(player)
    return player


@router.patch("/{player_id}", response_model=PlayerResponse)
def update_player(
    competition_id: UUID,
    team_id: UUID,
    player_id: UUID,
    payload: PlayerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    competition = get_competition_or_404(competition_id, current_user, db)
    _editable(competition)
    _team_or_404(db, competition_id, team_id)
    player = _player_or_404(db, team_id, player_id)

    updates = payload.model_dump(exclude_unset=True)
    if updates.get("name") is None:
        updates.pop("name", None)  # a name can't be cleared
    _check_unique(db, team_id, updates.get("name"), updates.get("shirt_number"), exclude=player.id)

    for field, value in updates.items():
        setattr(player, field, value)
    _commit(db)
    db.refresh(player)
    return player


@router.delete("/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_player(
    competition_id: UUID,
    team_id: UUID,
    player_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    competition = get_competition_or_404(competition_id, current_user, db)
    _editable(competition)
    _team_or_404(db, competition_id, team_id)
    player = _player_or_404(db, team_id, player_id)

    in_events = db.query(MatchEvent.id).filter(
        or_(MatchEvent.player_id == player.id, MatchEvent.assist_player_id == player.id)
    ).first()
    if in_events:
        raise HTTPException(
            status_code=400,
            detail=f"{player.name} has goals, assists or cards recorded. Remove them from those matches first",
        )

    db.delete(player)
    db.commit()
