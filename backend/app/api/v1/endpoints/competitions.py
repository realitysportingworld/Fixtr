from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_viewable_competition_or_404
from app.core.security import get_current_user
from app.db.base import get_db
from app.models.models import Competition, CompetitionStatus, Fixture, Result, Standing, User
from app.schemas.competition import CompetitionCreate, CompetitionUpdate, CompetitionResponse, FREE_TIER_LIMIT
from app.services.scoring import (
    draws_allowed, get_default_scoring, get_scoring_presets, lower_score_wins, winning_side,
)
from app.services.standings import recalculate_all_standings

router = APIRouter()


@router.get("/scoring-defaults")
def get_scoring_defaults():
    """Return default scoring configs for all sports."""
    from app.services.scoring import SPORT_DEFAULTS
    return SPORT_DEFAULTS


@router.get("/scoring-presets")
def get_presets():
    """Named scoring rule sets per sport (e.g. basketball: FIBA, NBA); the first is the default."""
    from app.models.models import SportType
    return {sport.value: get_scoring_presets(sport.value) for sport in SportType}


@router.get("/public", response_model=list[CompetitionResponse])
def search_public_competitions(
    q: str = Query(default="", max_length=100),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=10_000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Find competitions other users have made public, by name or owner username."""
    query = (
        db.query(Competition)
        .join(User, Competition.owner_id == User.id)
        .options(joinedload(Competition.owner))
        .filter(Competition.is_public.is_(True))
    )
    term = q.strip()
    if term:
        # Treat % and _ in the search text literally
        escaped = term.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        pattern = f"%{escaped}%"
        query = query.filter(or_(
            Competition.name.ilike(pattern, escape="\\"),
            User.username.ilike(pattern, escape="\\"),
        ))
    return query.order_by(Competition.created_at.desc(), Competition.id).offset(offset).limit(limit).all()


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
    data["format_config"] = payload.format_config.model_dump(exclude_none=True) if payload.format_config else None
    # Any keys the user leaves out fall back to the sport's defaults
    data["scoring_config"] = {**get_default_scoring(data["sport"]), **(data["scoring_config"] or {})}

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
    return get_viewable_competition_or_404(competition_id, current_user, db)


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

    updates = payload.model_dump(exclude_unset=True)
    has_fixtures = db.query(Fixture.id).filter(Fixture.competition_id == competition_id).first() is not None

    if updates.get("status") is not None:
        # Draft means "teams editable, no fixtures yet"; once fixtures exist the
        # competition can only be active, completed or cancelled.
        if has_fixtures:
            allowed = {CompetitionStatus.ACTIVE, CompetitionStatus.COMPLETED, CompetitionStatus.CANCELLED}
        else:
            allowed = {CompetitionStatus.DRAFT, CompetitionStatus.CANCELLED}
        if updates["status"] not in allowed:
            raise HTTPException(
                status_code=400,
                detail=f"Status can't be '{updates['status'].value}' "
                       f"{'once fixtures exist' if has_fixtures else 'before fixtures are generated'}",
            )

    scoring_changed = False
    if updates.get("scoring_config") is not None:
        old_lower_wins = lower_score_wins(competition)
        updates["scoring_config"] = {**(competition.scoring_config or {}), **updates["scoring_config"]}
        competition.scoring_config = updates.pop("scoring_config")
        scoring_changed = True

        if not draws_allowed(competition) and has_drawn_table_results(db, competition):
            raise HTTPException(
                status_code=400,
                detail="Can't turn off draws: some results are already draws. Edit those first",
            )

        if lower_score_wins(competition) != old_lower_wins:
            if not reassign_winners(db, competition):
                raise HTTPException(
                    status_code=400,
                    detail="Can't change lower_wins once knockout matches have results",
                )
    elif "scoring_config" in updates:
        updates.pop("scoring_config")  # explicit null — keep the current rules

    for field, value in updates.items():
        if value is None and field != "description":
            continue  # name and status can't be cleared
        setattr(competition, field, value)

    db.commit()

    if scoring_changed and has_fixtures:
        recalculate_all_standings(db, competition)

    db.refresh(competition)
    return competition


def has_drawn_table_results(db: Session, competition: Competition) -> bool:
    return db.query(Result.id).join(Fixture, Result.fixture_id == Fixture.id).filter(
        Fixture.competition_id == competition.id,
        Fixture.knockout_round.is_(None),
        Result.home_score == Result.away_score,
    ).first() is not None


def reassign_winners(db: Session, competition: Competition) -> bool:
    """
    Recompute winner_id for existing results after the lower_wins rule flips.
    Returns False (changing nothing) if any knockout match already has a
    result, since that would invalidate the bracket. Does NOT commit.
    """
    results = (
        db.query(Result, Fixture)
        .join(Fixture, Result.fixture_id == Fixture.id)
        .filter(Fixture.competition_id == competition.id)
        .all()
    )
    if any(fixture.knockout_round for _, fixture in results):
        return False

    lower_wins = lower_score_wins(competition)
    for result, fixture in results:
        side = winning_side(result.home_score, result.away_score, lower_wins)
        result.winner_id = {"home": fixture.home_team_id, "away": fixture.away_team_id}.get(side)
    return True


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

    # Standings have no ORM relationship to cascade through, so clear them first
    db.query(Standing).filter(Standing.competition_id == competition_id).delete()
    db.delete(competition)
    db.commit()
