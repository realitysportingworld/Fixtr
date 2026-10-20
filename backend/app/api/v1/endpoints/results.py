from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.models import Competition, Fixture, FixtureStatus, Result, User
from app.schemas.result import ResultCreate, ResultResponse
from app.services.knockout import advance_knockout_round, next_round_fixture
from app.services.scoring import lower_score_wins, winning_side
from app.services.standings import recalculate_standings

router = APIRouter()


def get_competition_or_404(competition_id: UUID, user: User, db: Session) -> Competition:
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.owner_id == user.id,
    ).first()
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    return competition


def get_fixture_or_404(fixture_id: UUID, competition_id: UUID, db: Session) -> Fixture:
    fixture = db.query(Fixture).filter(
        Fixture.id == fixture_id,
        Fixture.competition_id == competition_id,
    ).first()
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return fixture


def determine_winner(competition: Competition, fixture: Fixture, payload: ResultCreate) -> UUID | None:
    """Validate the result for this fixture and return the winning team id (None = draw)."""
    if fixture.is_bye:
        raise HTTPException(status_code=400, detail="Cannot record a result for a BYE")

    side = winning_side(payload.home_score, payload.away_score, lower_score_wins(competition))
    if side is None and fixture.knockout_round:
        raise HTTPException(status_code=400, detail="Knockout matches cannot end in a draw")

    if side == "home":
        return fixture.home_team_id
    if side == "away":
        return fixture.away_team_id
    return None


@router.post("/{fixture_id}/result", response_model=ResultResponse, status_code=status.HTTP_201_CREATED)
def record_result(
    competition_id: UUID,
    fixture_id: UUID,
    payload: ResultCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    competition = get_competition_or_404(competition_id, current_user, db)
    fixture = get_fixture_or_404(fixture_id, competition_id, db)

    if fixture.result:
        raise HTTPException(status_code=400, detail="Result already recorded. Use PUT to update it.")

    winner_id = determine_winner(competition, fixture, payload)

    result = Result(
        fixture_id=fixture_id,
        home_score=payload.home_score,
        away_score=payload.away_score,
        extra_data=payload.extra_data,
        winner_id=winner_id,
    )
    db.add(result)
    fixture.status = FixtureStatus.COMPLETED
    db.commit()
    db.refresh(result)

    if fixture.knockout_round:
        advance_knockout_round(db, competition_id, fixture.round_number)
    else:
        recalculate_standings(db, competition_id, group_id=fixture.group_id)

    return result


@router.put("/{fixture_id}/result", response_model=ResultResponse)
def update_result(
    competition_id: UUID,
    fixture_id: UUID,
    payload: ResultCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    competition = get_competition_or_404(competition_id, current_user, db)
    fixture = get_fixture_or_404(fixture_id, competition_id, db)

    if not fixture.result:
        raise HTTPException(status_code=404, detail="No result recorded yet. Use POST to record it.")

    winner_id = determine_winner(competition, fixture, payload)
    old_winner_id = fixture.result.winner_id

    # If the knockout winner changed and the next round already exists, swap
    # the new winner into it — unless that match has already been played.
    if fixture.knockout_round and winner_id != old_winner_id:
        next_fixture = next_round_fixture(db, fixture)
        if next_fixture:
            if next_fixture.result:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot change the winner: their next-round match already has a result",
                )
            if next_fixture.home_team_id == old_winner_id:
                next_fixture.home_team_id = winner_id
            elif next_fixture.away_team_id == old_winner_id:
                next_fixture.away_team_id = winner_id

    fixture.result.home_score = payload.home_score
    fixture.result.away_score = payload.away_score
    fixture.result.extra_data = payload.extra_data
    fixture.result.winner_id = winner_id

    db.commit()
    db.refresh(fixture.result)

    if fixture.knockout_round:
        advance_knockout_round(db, competition_id, fixture.round_number)
    else:
        recalculate_standings(db, competition_id, group_id=fixture.group_id)

    return fixture.result
