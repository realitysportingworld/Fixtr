"""
Knockout bracket service.

Creates first-round fixtures (including BYEs) and, after a result is recorded
for a knockout fixture, checks whether the entire round is now complete. If so,
pairs winners in bracket order and creates the next round's fixtures. Handles
both KNOCKOUT and the knockout phase of GROUP_KNOCKOUT.
"""
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.models import Competition, CompetitionStatus, Fixture, FixtureStatus
from app.services.fixture_generator import bracket_size, get_knockout_round_label


def create_first_round(
    db: Session,
    competition_id: UUID,
    entries: list,
    round_number: int,
) -> list[Fixture]:
    """
    Add first-round knockout fixtures from (home_id, away_id) entries in bracket
    order. An entry with away_id None is a BYE, stored as an already-completed
    fixture so the home team advances automatically. Does NOT commit.
    """
    label = get_knockout_round_label(bracket_size(len(entries) * 2))
    fixtures = []
    for position, (home_id, away_id) in enumerate(entries):
        f = Fixture(
            competition_id=competition_id,
            home_team_id=home_id,
            away_team_id=away_id,
            round_number=round_number,
            knockout_round=label,
            bracket_position=position,
            status=FixtureStatus.COMPLETED if away_id is None else FixtureStatus.SCHEDULED,
        )
        db.add(f)
        fixtures.append(f)
    return fixtures


def knockout_started(db: Session, competition_id: UUID) -> bool:
    return db.query(Fixture.id).filter(
        Fixture.competition_id == competition_id,
        Fixture.knockout_round.isnot(None),
    ).first() is not None


def fixture_winner(fixture: Fixture) -> Optional[UUID]:
    if fixture.is_bye:
        return fixture.home_team_id
    if fixture.status != FixtureStatus.COMPLETED or fixture.result is None:
        return None
    return fixture.result.winner_id


def _round_fixtures(db: Session, competition_id: UUID, round_number: int) -> list[Fixture]:
    return (
        db.query(Fixture)
        .filter(
            Fixture.competition_id == competition_id,
            Fixture.round_number == round_number,
            Fixture.knockout_round.isnot(None),
        )
        .order_by(Fixture.bracket_position, Fixture.created_at)
        .all()
    )


def next_round_fixture(db: Session, fixture: Fixture) -> Optional[Fixture]:
    """The fixture the winner of `fixture` plays in next, if it has been created."""
    if fixture.bracket_position is None:
        return None
    return db.query(Fixture).filter(
        Fixture.competition_id == fixture.competition_id,
        Fixture.round_number == fixture.round_number + 1,
        Fixture.knockout_round.isnot(None),
        Fixture.bracket_position == fixture.bracket_position // 2,
    ).first()


def advance_knockout_round(db: Session, competition_id: UUID, round_number: int) -> list:
    """
    Check if all knockout fixtures in the given round are complete.
    If so, create next-round fixtures pairing winners in bracket order.
    If the round was the Final, mark the competition completed.

    Safe to call repeatedly: does nothing if the next round already exists.

    Returns list of newly created Fixture objects (empty if round is
    incomplete, the next round already exists, or this was the Final).
    """
    round_fixtures = _round_fixtures(db, competition_id, round_number)
    if not round_fixtures:
        return []

    winners = [fixture_winner(f) for f in round_fixtures]
    if any(w is None for w in winners):
        return []  # round not complete yet

    # Final has exactly 1 match — tournament is over
    if len(round_fixtures) == 1:
        competition = db.query(Competition).filter(Competition.id == competition_id).first()
        if competition and competition.status == CompetitionStatus.ACTIVE:
            competition.status = CompetitionStatus.COMPLETED
            db.commit()
        return []

    next_round = round_number + 1
    if _round_fixtures(db, competition_id, next_round):
        return []

    label = get_knockout_round_label(len(winners))

    new_fixtures = []
    for i in range(0, len(winners), 2):
        f = Fixture(
            competition_id=competition_id,
            home_team_id=winners[i],
            away_team_id=winners[i + 1],
            round_number=next_round,
            knockout_round=label,
            bracket_position=i // 2,
        )
        db.add(f)
        new_fixtures.append(f)

    db.commit()
    return new_fixtures
