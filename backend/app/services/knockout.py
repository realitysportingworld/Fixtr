"""
Knockout bracket advancement service.

After a result is recorded for a knockout fixture, checks whether the entire
round is now complete. If so, pairs winners in order and creates the next
round's fixtures. Handles both KNOCKOUT and the knockout phase of GROUP_KNOCKOUT.
"""
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.models import Fixture, FixtureStatus
from app.services.fixture_generator import get_knockout_round_label


def advance_knockout_round(db: Session, competition_id: UUID, round_number: int) -> list:
    """
    Check if all knockout fixtures in the given round are complete.
    If so, create next-round fixtures pairing winners in bracket order.

    Returns list of newly created Fixture objects (empty if round is
    incomplete, there's a draw, or this was the Final).
    """
    round_fixtures = (
        db.query(Fixture)
        .filter(
            Fixture.competition_id == competition_id,
            Fixture.round_number == round_number,
            Fixture.knockout_round.isnot(None),
        )
        .order_by(Fixture.created_at)
        .all()
    )

    if not round_fixtures:
        return []

    # Final has exactly 1 match — tournament is over
    if len(round_fixtures) == 1:
        return []

    # Round not complete yet
    if any(f.status != FixtureStatus.COMPLETED for f in round_fixtures):
        return []

    # Collect winners in bracket order
    winners = []
    for fixture in round_fixtures:
        if fixture.result is None or fixture.result.winner_id is None:
            # Draw in knockout — cannot advance (caller should enforce no-draw rule)
            return []
        winners.append(fixture.result.winner_id)

    next_round = round_number + 1
    label = get_knockout_round_label(len(winners))

    new_fixtures = []
    for i in range(0, len(winners), 2):
        f = Fixture(
            competition_id=competition_id,
            home_team_id=winners[i],
            away_team_id=winners[i + 1],
            round_number=next_round,
            knockout_round=label,
        )
        db.add(f)
        new_fixtures.append(f)

    db.commit()
    return new_fixtures
