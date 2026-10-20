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

from app.models.models import (
    Competition, CompetitionFormat, CompetitionStatus,
    Fixture, FixtureStatus, Group, Result, Standing, Team,
)
from app.services.scoring import lower_score_wins, winning_side


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
    lower_wins = lower_score_wins(competition)

    # Fetch all completed non-knockout fixtures in scope. group_id=None means
    # the ungrouped (league) table, not "every fixture in the competition".
    fixtures = (
        db.query(Fixture)
        .filter(
            Fixture.competition_id == competition_id,
            Fixture.status == FixtureStatus.COMPLETED,
            Fixture.knockout_round.is_(None),
            Fixture.group_id == group_id if group_id else Fixture.group_id.is_(None),
        )
        .all()
    )

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

        side = winning_side(result.home_score, result.away_score, lower_wins)
        if side == "home":
            home["wins"] += 1
            home["points"] += scoring.get("win", 3)
            away["losses"] += 1
            away["points"] += scoring.get("loss", 0)
        elif side == "away":
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
    db.query(Standing).filter(
        Standing.competition_id == competition_id,
        Standing.group_id == group_id if group_id else Standing.group_id.is_(None),
    ).delete()

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
    return new_standings


def recalculate_all_standings(db: Session, competition: Competition) -> None:
    """Rebuild every table in the competition (league table, or each group's)."""
    if competition.format == CompetitionFormat.GROUP_KNOCKOUT:
        for group in db.query(Group).filter(Group.competition_id == competition.id).all():
            recalculate_standings(db, competition.id, group_id=group.id)
    else:
        recalculate_standings(db, competition.id)


def sync_league_completion(db: Session, competition: Competition) -> None:
    """
    A league is completed once every fixture has been played, and reopens
    if new unplayed fixtures are added. Knockout formats complete when their
    Final is played (see services/knockout.py).
    """
    if competition.format != CompetitionFormat.LEAGUE:
        return
    if competition.status not in (CompetitionStatus.ACTIVE, CompetitionStatus.COMPLETED):
        return

    statuses = [
        s for (s,) in db.query(Fixture.status).filter(Fixture.competition_id == competition.id).all()
    ]
    all_played = bool(statuses) and all(s == FixtureStatus.COMPLETED for s in statuses)
    new_status = CompetitionStatus.COMPLETED if all_played else CompetitionStatus.ACTIVE
    if competition.status != new_status:
        competition.status = new_status
        db.commit()


def ranked_table(
    db: Session,
    competition: Competition,
    teams: list[Team],
    group_id: Optional[UUID] = None,
) -> list[dict]:
    """
    Build sorted table rows (dicts) for the given teams from stored Standing rows.
    Teams without results appear with zeros. group_id narrows the Standing rows
    read; None reads all of the competition's rows.

    Sorted by points, then goal difference, then goals scored (both reversed
    for lower-wins sports like golf), then team name.
    """
    query = db.query(Standing).filter(Standing.competition_id == competition.id)
    if group_id:
        query = query.filter(Standing.group_id == group_id)
    standings_map = {s.team_id: s for s in query.all()}

    rows = []
    for team in teams:
        s = standings_map.get(team.id)
        rows.append({
            "team_id": team.id,
            "team_name": team.name,
            "played": s.played if s else 0,
            "wins": s.wins if s else 0,
            "draws": s.draws if s else 0,
            "losses": s.losses if s else 0,
            "goals_for": s.goals_for if s else 0,
            "goals_against": s.goals_against if s else 0,
            "goal_difference": (s.goals_for - s.goals_against) if s else 0,
            "points": s.points if s else 0,
        })

    sign = 1 if lower_score_wins(competition) else -1
    rows.sort(key=lambda r: (-r["points"], sign * r["goal_difference"], sign * r["goals_for"], r["team_name"]))
    return rows
