from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.models import Competition, Fixture, FixtureStatus, Result, User
from app.schemas.result import ResultCreate, ResultResponse
from app.services.knockout import advance_knockout_round
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

    winner_id = None
    if payload.home_score > payload.away_score:
        winner_id = fixture.home_team_id
    elif payload.away_score > payload.home_score:
        winner_id = fixture.away_team_id

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
    get_competition_or_404(competition_id, current_user, db)
    fixture = get_fixture_or_404(fixture_id, competition_id, db)

    if not fixture.result:
        raise HTTPException(status_code=404, detail="No result recorded yet. Use POST to record it.")

    winner_id = None
    if payload.home_score > payload.away_score:
        winner_id = fixture.home_team_id
    elif payload.away_score > payload.home_score:
        winner_id = fixture.away_team_id

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
