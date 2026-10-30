"""
Standings calculation service.

Recalculates standings for a competition (or a single group within it)
from scratch based on all completed fixture results.

Scoring config example (stored on Competition.scoring_config):
    {"win": 3, "draw": 1, "loss": 0}  ← football
    {"win": 2, "draw": 0, "loss": 1}  ← some cup formats
"""
from itertools import groupby
from typing import Callable, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.models import (
    Competition, CompetitionFormat, CompetitionStatus,
    Fixture, FixtureStatus, Group, Result, Standing, Team,
)
from app.services.scoring import lower_score_wins, ranking_mode, tiebreak_mode, winning_side


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


def _runs(rows: list[dict], key: Callable) -> list[list[dict]]:
    """Split already-sorted rows into runs of rows with equal keys."""
    return [list(run) for _, run in groupby(rows, key=key)]


def _table_fixtures(db: Session, competition_id: UUID, group_id: Optional[UUID]) -> list[Fixture]:
    """Completed table-stage (non-knockout) fixtures, in one group if given."""
    query = db.query(Fixture).filter(
        Fixture.competition_id == competition_id,
        Fixture.status == FixtureStatus.COMPLETED,
        Fixture.knockout_round.is_(None),
    )
    if group_id:
        query = query.filter(Fixture.group_id == group_id)
    return query.all()


def _mini_table_keys(
    fixtures: list[Fixture], team_ids: set, scoring: dict, lower_wins: bool, win_pct: bool,
) -> dict:
    """
    Sort key per team from a mini-table of the matches among team_ids:
    points (or win percentage), then score difference, then scored.
    """
    mini = {t: {"points": 0, "wins": 0, "played": 0, "for": 0, "against": 0} for t in team_ids}
    for f in fixtures:
        if f.result is None or f.home_team_id not in mini or f.away_team_id not in mini:
            continue
        home, away = mini[f.home_team_id], mini[f.away_team_id]
        hs, as_ = f.result.home_score, f.result.away_score
        for team, scored, conceded in ((home, hs, as_), (away, as_, hs)):
            team["played"] += 1
            team["for"] += scored
            team["against"] += conceded
        side = winning_side(hs, as_, lower_wins)
        if side is None:
            home["points"] += scoring.get("draw", 1)
            away["points"] += scoring.get("draw", 1)
        else:
            winner, loser = (home, away) if side == "home" else (away, home)
            winner["wins"] += 1
            winner["points"] += scoring.get("win", 3)
            loser["points"] += scoring.get("loss", 0)

    sign = 1 if lower_wins else -1

    def key(m: dict) -> tuple:
        first = -(m["wins"] / m["played"] if m["played"] else 0) if win_pct else -m["points"]
        return (first, sign * (m["for"] - m["against"]), sign * m["for"])

    return {t: key(m) for t, m in mini.items()}


def _order_by_head_to_head(level: list[dict], head_to_head: Callable, fallback: Callable) -> list[dict]:
    """
    Order teams that are level, by a mini-table of their matches against each
    other. Teams still level are re-checked among themselves (UEFA style); a
    set the mini-table can't split at all is ordered by `fallback`.
    """
    if len(level) < 2:
        return level
    keys = head_to_head({r["team_id"] for r in level})
    key = lambda r: keys[r["team_id"]]  # noqa: E731
    runs = _runs(sorted(level, key=key), key)
    if len(runs) == 1:
        return fallback(level)
    ordered = []
    for run in runs:
        ordered.extend(_order_by_head_to_head(run, head_to_head, fallback))
    return ordered


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

    Sorted by points (or win percentage then wins, for "win_pct" ranking),
    then by the competition's tiebreak (scoring.tiebreak_mode): goal
    difference and goals scored (both reversed for lower-wins sports like
    golf) and head-to-head, in either order; team name last.
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
            "win_pct": round(s.wins / s.played, 3) if s and s.played else 0.0,
        })

    lower_wins = lower_score_wins(competition)
    sign = 1 if lower_wins else -1
    win_pct = ranking_mode(competition) == "win_pct"
    if win_pct:
        primary = lambda r: (-r["win_pct"], -r["wins"])  # noqa: E731
    else:
        primary = lambda r: (-r["points"],)  # noqa: E731
    overall = lambda r: (sign * r["goal_difference"], sign * r["goals_for"])  # noqa: E731

    played: list[list[Fixture]] = []  # loaded only if some teams are level

    def head_to_head(team_ids: set) -> dict:
        """Mini-table key per team, from matches between the given teams only."""
        if not played:
            played.append(_table_fixtures(db, competition.id, group_id))
        return _mini_table_keys(played[0], team_ids, competition.scoring_config or DEFAULT_SCORING,
                                lower_wins, win_pct)

    by_name = lambda group: sorted(group, key=lambda r: r["team_name"])  # noqa: E731
    ranked = []
    if tiebreak_mode(competition) == "head_to_head":
        # Level teams: head-to-head first, then overall difference and scored
        rows.sort(key=primary)
        then_overall = lambda group: sorted(group, key=lambda r: (*overall(r), r["team_name"]))  # noqa: E731
        for level in _runs(rows, primary):
            ranked.extend(_order_by_head_to_head(level, head_to_head, then_overall))
    else:
        # Level on difference and scored too: head-to-head, then name
        full = lambda r: (*primary(r), *overall(r))  # noqa: E731
        rows.sort(key=full)
        for level in _runs(rows, full):
            ranked.extend(_order_by_head_to_head(level, head_to_head, by_name))
    rows = ranked

    if rows:
        leader = rows[0]
        for r in rows:
            r["games_behind"] = ((leader["wins"] - r["wins"]) + (r["losses"] - leader["losses"])) / 2
    return rows
