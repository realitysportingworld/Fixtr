"""
Standings calculation service.

Recalculates standings for a competition (or a single group within it)
from scratch based on all completed fixture results.

Scoring config example (stored on Competition.scoring_config):
    {"win": 3, "draw": 1, "loss": 0}  ← football
    {"win": 2, "draw": 0, "loss": 1}  ← some cup formats
"""
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.models import Competition, Fixture, FixtureStatus, Result, Standing


DEFAULT_SCORING = {"win": 3, "draw": 1, "loss": 0}


def recalculate_standings(
    db: Session,
    competition_id: UUID,
    group_id: Optional[UUID] = None,
) -> list[Standing]:
    """
    Wipe and rebuild standing rows for a competition (or group).
    Call this after any result is recorded or updated.
    """
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if not competition:
        raise ValueError(f"Competition {competition_id} not found")

    scoring = competition.scoring_config or DEFAULT_SCORING

    # Fetch all completed fixtures in scope
    query = (
        db.query(Fixture)
        .filter(
            Fixture.competition_id == competition_id,
            Fixture.status == FixtureStatus.COMPLETED,
        )
    )
    if group_id:
        query = query.filter(Fixture.group_id == group_id)

    fixtures = query.all()

    # Aggregate stats per team
    stats: dict[UUID, dict] = {}

    def get_or_create(team_id: UUID) -> dict:
        if team_id not in stats:
            stats[team_id] = {
                "played": 0, "wins": 0, "draws": 0, "losses": 0,
                "goals_for": 0, "goals_against": 0, "points": 0,
            }
        return stats[team_id]

    for fixture in fixtures:
        result: Result = fixture.result
        if not result:
            continue

        home = get_or_create(fixture.home_team_id)
        away = get_or_create(fixture.away_team_id)

        home["played"] += 1
        away["played"] += 1
        home["goals_for"] += result.home_score
        home["goals_against"] += result.away_score
        away["goals_for"] += result.away_score
        away["goals_against"] += result.home_score

        if result.home_score > result.away_score:
            home["wins"] += 1
            home["points"] += scoring.get("win", 3)
            away["losses"] += 1
            away["points"] += scoring.get("loss", 0)
        elif result.away_score > result.home_score:
            away["wins"] += 1
            away["points"] += scoring.get("win", 3)
            home["losses"] += 1
            home["points"] += scoring.get("loss", 0)
        else:
            home["draws"] += 1
            home["points"] += scoring.get("draw", 1)
            away["draws"] += 1
            away["points"] += scoring.get("draw", 1)

    # Delete existing standing rows in scope
    delete_query = db.query(Standing).filter(Standing.competition_id == competition_id)
    if group_id:
        delete_query = delete_query.filter(Standing.group_id == group_id)
    delete_query.delete()

    # Write fresh rows
    new_standings = []
    for team_id, s in stats.items():
        standing = Standing(
            competition_id=competition_id,
            group_id=group_id,
            team_id=team_id,
            **s,
        )
        db.add(standing)
        new_standings.append(standing)

    db.commit()
    return sorted(new_standings, key=lambda x: (-x.points, -(x.goals_for - x.goals_against)))
