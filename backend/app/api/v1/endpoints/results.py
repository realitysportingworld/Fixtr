from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_competition_or_404
from app.core.security import get_current_user
from app.db.base import get_db
from app.models.models import (
    Competition, CompetitionFormat, CompetitionStatus, Fixture, FixtureStatus, Result, User,
)
from app.schemas.result import ResultCreate, ResultResponse
from app.services.knockout import advance_knockout_round, knockout_started, next_round_fixtures, other_leg
from app.services.scoring import draws_allowed, lower_score_wins, winning_side
from app.services.standings import recalculate_standings, sync_league_completion

router = APIRouter()

# Formats whose table stage is frozen once the knockout begins
STAGED_FORMATS = (CompetitionFormat.GROUP_KNOCKOUT, CompetitionFormat.LEAGUE_PHASE)


def get_fixture_or_404(fixture_id: UUID, competition_id: UUID, db: Session) -> Fixture:
    fixture = db.query(Fixture).filter(
        Fixture.id == fixture_id,
        Fixture.competition_id == competition_id,
    ).first()
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return fixture


def _side_team(fixture: Fixture, side):
    return {"home": fixture.home_team_id, "away": fixture.away_team_id}.get(side)


def _decide_level(payload: ResultCreate, what: str):
    if payload.tiebreak_winner is None:
        raise HTTPException(
            status_code=400,
            detail=f"Knockout ties can't end in a draw: {what} is level, so say who won the "
                   "tiebreak (e.g. penalties)",
        )
    return payload.tiebreak_winner


def tie_side(home_total: int, away_total: int, lower_wins: bool, previous_side=None):
    """Winning side of a knockout tie, keeping a previous tiebreak if it's level."""
    return winning_side(home_total, away_total, lower_wins) or previous_side


def determine_winner(db: Session, competition: Competition, fixture: Fixture, payload: ResultCreate) -> UUID | None:
    """Validate the result for this fixture and return the winning team id (None = draw / first leg)."""
    if competition.status == CompetitionStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Competition is cancelled")
    if fixture.is_bye:
        raise HTTPException(status_code=400, detail="Cannot record a result for a BYE")
    if (
        fixture.knockout_round is None
        and competition.format in STAGED_FORMATS
        and knockout_started(db, competition.id)
    ):
        raise HTTPException(
            status_code=400,
            detail="Group and league phase results are locked once the knockout phase has started",
        )

    lower_wins = lower_score_wins(competition)

    if fixture.knockout_round is None:
        side = winning_side(payload.home_score, payload.away_score, lower_wins)
        if side is None and not draws_allowed(competition):
            raise HTTPException(status_code=400, detail="Draws aren't allowed in this competition")
        return _side_team(fixture, side)

    if fixture.leg == 1:
        return None  # the tie is decided after the second leg

    if fixture.leg == 2:
        first_leg = other_leg(db, fixture)
        if first_leg is None or first_leg.result is None:
            raise HTTPException(status_code=400, detail="Enter the first leg's result first")
        # Leg 2's home team was the away side in leg 1
        home_total = payload.home_score + first_leg.result.away_score
        away_total = payload.away_score + first_leg.result.home_score
        side = winning_side(home_total, away_total, lower_wins) or _decide_level(payload, "the aggregate score")
        return _side_team(fixture, side)

    side = winning_side(payload.home_score, payload.away_score, lower_wins) or _decide_level(payload, "the score")
    return _side_team(fixture, side)


def move_winner_on(db: Session, fixture: Fixture, old_winner_id, new_winner_id) -> None:
    """
    A knockout tie's winner changed: swap the new winner into the next round's
    fixture(s), unless the next round has already been played. Does NOT commit.
    """
    if old_winner_id is None or old_winner_id == new_winner_id:
        return
    next_fixtures = next_round_fixtures(db, fixture)
    if any(f.result for f in next_fixtures):
        raise HTTPException(
            status_code=400,
            detail="Cannot change the winner: their next-round match already has a result",
        )
    for f in next_fixtures:
        if f.home_team_id == old_winner_id:
            f.home_team_id = new_winner_id
        elif f.away_team_id == old_winner_id:
            f.away_team_id = new_winner_id


def after_result(db: Session, competition: Competition, fixture: Fixture) -> None:
    if fixture.knockout_round:
        advance_knockout_round(db, competition.id, fixture.round_number)
    else:
        recalculate_standings(db, competition.id, group_id=fixture.group_id)
        sync_league_completion(db, competition)


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

    winner_id = determine_winner(db, competition, fixture, payload)

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

    after_result(db, competition, fixture)
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

    winner_id = determine_winner(db, competition, fixture, payload)

    if fixture.knockout_round and fixture.leg == 1:
        # Editing the first leg after the second was played re-decides the tie
        # on the new aggregate; if it is now level, the recorded tiebreak stands.
        second_leg = other_leg(db, fixture)
        if second_leg and second_leg.result:
            old = second_leg.result.winner_id
            previous_side = "home" if old == second_leg.home_team_id else "away"
            side = tie_side(
                second_leg.result.home_score + payload.away_score,
                second_leg.result.away_score + payload.home_score,
                lower_score_wins(competition),
                previous_side,
            )
            new = _side_team(second_leg, side)
            move_winner_on(db, fixture, old, new)
            second_leg.result.winner_id = new
    elif fixture.knockout_round:
        move_winner_on(db, fixture, fixture.result.winner_id, winner_id)

    fixture.result.home_score = payload.home_score
    fixture.result.away_score = payload.away_score
    fixture.result.extra_data = payload.extra_data
    fixture.result.winner_id = winner_id

    db.commit()
    db.refresh(fixture.result)

    after_result(db, competition, fixture)
    return fixture.result


@router.delete("/{fixture_id}/result", status_code=status.HTTP_204_NO_CONTENT)
def clear_result(
    competition_id: UUID,
    fixture_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Un-play a match: remove its result and put it back to scheduled. A decided
    knockout tie also loses its next-round tie (rebuilt when the tie is decided
    again), which is refused once that next-round match has a result.
    """
    competition = get_competition_or_404(competition_id, current_user, db)
    fixture = get_fixture_or_404(fixture_id, competition_id, db)

    if competition.status == CompetitionStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Competition is cancelled")
    if fixture.is_bye:
        raise HTTPException(status_code=400, detail="A BYE has no result to clear")
    if not fixture.result:
        raise HTTPException(status_code=404, detail="No result recorded yet")

    if fixture.knockout_round is None:
        if competition.format in STAGED_FORMATS and knockout_started(db, competition.id):
            raise HTTPException(
                status_code=400,
                detail="Group and league phase results are locked once the knockout phase has started",
            )
    elif fixture.leg == 1:
        second_leg = other_leg(db, fixture)
        if second_leg and second_leg.result:
            raise HTTPException(status_code=400, detail="Clear the second leg's result first")
    else:
        next_fixtures = next_round_fixtures(db, fixture)
        if any(f.result for f in next_fixtures):
            raise HTTPException(
                status_code=400,
                detail="Cannot clear: the winner's next-round match already has a result",
            )
        for f in next_fixtures:
            db.delete(f)
        if competition.status == CompetitionStatus.COMPLETED:
            competition.status = CompetitionStatus.ACTIVE  # the final is undecided again

    db.delete(fixture.result)
    fixture.status = FixtureStatus.SCHEDULED
    db.commit()

    if fixture.knockout_round is None:
        recalculate_standings(db, competition.id, group_id=fixture.group_id)
        sync_league_completion(db, competition)
