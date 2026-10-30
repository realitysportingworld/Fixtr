"""
Knockout bracket service.

Creates first-round fixtures (including BYEs) and, after a result is recorded
for a knockout fixture, checks whether the entire round is now complete. If so,
pairs winners in bracket order and creates the next round's fixtures. Handles
KNOCKOUT and the knockout phases of GROUP_KNOCKOUT and LEAGUE_PHASE.

A tie is everything at one bracket_position in a round: a single match, or two
legs (leg 1 and leg 2, home and away swapped) when the competition's
format_config has two_legged. A two-legged tie is decided by leg 2's winner_id,
which results.py works out on aggregate. The final is always a single match.
"""
from itertools import groupby
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.models import Competition, CompetitionStatus, Fixture, FixtureStatus
from app.services.fixture_generator import bracket_size, get_knockout_round_label


def is_two_legged(competition: Competition) -> bool:
    return bool((competition.format_config or {}).get("two_legged"))


def _add_tie(
    db: Session, competition_id: UUID, home_id, away_id, round_number: int,
    label: str, position: int, two_legged: bool,
) -> list[Fixture]:
    """
    Add one tie. home_id is the higher seed: in a two-legged tie they host the
    second leg. Does NOT commit.
    """
    common = dict(competition_id=competition_id, round_number=round_number,
                  knockout_round=label, bracket_position=position)
    if away_id is None:  # BYE: already completed, home team goes through
        fixtures = [Fixture(home_team_id=home_id, away_team_id=None, status=FixtureStatus.COMPLETED, **common)]
    elif two_legged:
        fixtures = [
            Fixture(home_team_id=away_id, away_team_id=home_id, leg=1, **common),
            Fixture(home_team_id=home_id, away_team_id=away_id, leg=2, **common),
        ]
    else:
        fixtures = [Fixture(home_team_id=home_id, away_team_id=away_id, **common)]
    for f in fixtures:
        db.add(f)
    return fixtures


def create_first_round(
    db: Session,
    competition_id: UUID,
    entries: list,
    round_number: int,
    two_legged: bool = False,
    label: Optional[str] = None,
) -> list[Fixture]:
    """
    Add first-round knockout fixtures from (home_id, away_id) entries in bracket
    order. An entry with away_id None is a BYE, stored as an already-completed
    fixture so the home team advances automatically. Does NOT commit.
    """
    label = label or get_knockout_round_label(bracket_size(len(entries) * 2))
    # A first round of one tie is the final, which is never two-legged
    two_legged = two_legged and len(entries) > 1
    fixtures = []
    for position, (home_id, away_id) in enumerate(entries):
        fixtures.extend(_add_tie(db, competition_id, home_id, away_id, round_number, label, position, two_legged))
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


def tie_winner(tie: list[Fixture]) -> Optional[UUID]:
    """Winner of a single match, or of a two-legged tie (decided on leg 2)."""
    deciding = next((f for f in tie if f.leg == 2), tie[0])
    return fixture_winner(deciding)


def _round_fixtures(db: Session, competition_id: UUID, round_number: int) -> list[Fixture]:
    return (
        db.query(Fixture)
        .filter(
            Fixture.competition_id == competition_id,
            Fixture.round_number == round_number,
            Fixture.knockout_round.isnot(None),
        )
        .order_by(Fixture.bracket_position, Fixture.leg, Fixture.created_at)
        .all()
    )


def _ties(fixtures: list[Fixture]) -> list[list[Fixture]]:
    """Group a round's fixtures (sorted by bracket_position) into ties."""
    return [list(group) for _, group in groupby(fixtures, key=lambda f: f.bracket_position)]


def other_leg(db: Session, fixture: Fixture) -> Optional[Fixture]:
    if fixture.leg is None:
        return None
    return db.query(Fixture).filter(
        Fixture.competition_id == fixture.competition_id,
        Fixture.round_number == fixture.round_number,
        Fixture.bracket_position == fixture.bracket_position,
        Fixture.leg == (2 if fixture.leg == 1 else 1),
    ).first()


def next_round_fixtures(db: Session, fixture: Fixture) -> list[Fixture]:
    """The fixture(s) the winner of `fixture`'s tie plays next, if created."""
    if fixture.bracket_position is None:
        return []
    return db.query(Fixture).filter(
        Fixture.competition_id == fixture.competition_id,
        Fixture.round_number == fixture.round_number + 1,
        Fixture.knockout_round.isnot(None),
        Fixture.bracket_position == fixture.bracket_position // 2,
    ).all()


def advance_knockout_round(db: Session, competition_id: UUID, round_number: int) -> list:
    """
    Check if all knockout ties in the given round are decided.
    If so, create next-round fixtures pairing winners in bracket order.
    If the round was the Final, mark the competition completed.

    Safe to call repeatedly: only next-round ties that don't exist yet are created.

    Returns list of newly created Fixture objects (empty if round is
    incomplete, the next round is already complete, or this was the Final).
    """
    ties = _ties(_round_fixtures(db, competition_id, round_number))
    if not ties:
        return []

    winners = [tie_winner(t) for t in ties]
    if any(w is None for w in winners):
        return []  # round not complete yet

    competition = db.query(Competition).filter(Competition.id == competition_id).first()

    # Final has exactly 1 tie — tournament is over
    if len(ties) == 1:
        if competition and competition.status == CompetitionStatus.ACTIVE:
            competition.status = CompetitionStatus.COMPLETED
            db.commit()
        return []

    # Ties already in the next round are kept; a cleared result removes its
    # next-round tie, which is rebuilt here once the round is decided again
    next_round = round_number + 1
    existing = {f.bracket_position for f in _round_fixtures(db, competition_id, next_round)}

    label = get_knockout_round_label(len(winners))
    two_legged = is_two_legged(competition) and len(winners) > 2  # the final is one match

    new_fixtures = []
    for i in range(0, len(winners), 2):
        if i // 2 in existing:
            continue
        new_fixtures.extend(_add_tie(
            db, competition_id, winners[i], winners[i + 1], next_round, label, i // 2, two_legged,
        ))

    if new_fixtures:
        db.commit()
    return new_fixtures
