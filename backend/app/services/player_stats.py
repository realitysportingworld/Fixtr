"""
Player stats: who scored, assisted and was booked in each match, and the
competition leaderboards built from that.

Events belong to a played match and are saved with its result. They're
optional and may be partial (an organiser can record only the scorers they
know), but never more goals for a side than the side scored. An own goal
counts for the other side and isn't credited to the player as a goal.
"""
from collections import Counter
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.models import Competition, Fixture, MatchEvent, MatchEventType, Player, Team
from app.schemas.result import MatchEventIn
from app.schemas.stats import CompetitionStats, DisciplineRow, PlayerStatRow

# Sports where a goal is one point on the scoreboard, so goals can be
# credited to players and checked against the score
STATS_SPORTS = ("football", "custom")
MAX_YELLOW_CARDS = 2  # a second yellow is a sending-off
MAX_RED_CARDS = 1


def player_stats_supported(competition: Competition) -> bool:
    sport = getattr(competition.sport, "value", competition.sport)
    return sport in STATS_SPORTS


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=400, detail=detail)


def _goals_by_side(events, team_of: dict, fixture: Fixture) -> Counter:
    """Goals each side is credited with: its players' goals plus the other side's own goals."""
    goals = Counter()
    for e in events:
        team = team_of[e.player_id]
        if e.type == MatchEventType.GOAL:
            goals[team] += 1
        elif e.type == MatchEventType.OWN_GOAL:
            other = fixture.away_team_id if team == fixture.home_team_id else fixture.home_team_id
            goals[other] += 1
    return goals


def _check_goals_fit_score(goals: Counter, fixture: Fixture, home_score: int, away_score: int, names: dict) -> None:
    for team_id, score in ((fixture.home_team_id, home_score), (fixture.away_team_id, away_score)):
        if goals[team_id] > score:
            raise _bad(
                f"{names.get(team_id, 'A team')} scored {score}, but {goals[team_id]} "
                f"goal{'s are' if goals[team_id] != 1 else ' is'} recorded for them. "
                "Fix the scorers or the score"
            )


def _team_names(db: Session, fixture: Fixture) -> dict:
    teams = db.query(Team.id, Team.name).filter(Team.id.in_([fixture.home_team_id, fixture.away_team_id])).all()
    return dict(teams)


def build_events(
    db: Session, competition: Competition, fixture: Fixture,
    home_score: int, away_score: int, events: list[MatchEventIn],
) -> list[MatchEvent]:
    """
    Validate a match's events against its squads and score and return them as
    unsaved MatchEvent rows. Raises HTTP 400 on anything inconsistent.
    """
    if not events:
        return []
    if not player_stats_supported(competition):
        raise _bad("Player stats aren't kept for this sport")
    if fixture.away_team_id is None:
        raise _bad("A BYE has no match events")

    wanted = {e.player_id for e in events} | {e.assist_player_id for e in events if e.assist_player_id}
    team_of = dict(
        db.query(Player.id, Player.team_id)
        .filter(Player.id.in_(wanted), Player.team_id.in_([fixture.home_team_id, fixture.away_team_id]))
        .all()
    )
    if len(team_of) != len(wanted):
        raise _bad("Every player in the match events must be in one of the two teams' squads")

    cards = Counter()
    for e in events:
        if e.assist_player_id and team_of[e.assist_player_id] != team_of[e.player_id]:
            raise _bad("A goal can only be assisted by a team-mate of the scorer")
        if e.type in (MatchEventType.YELLOW_CARD, MatchEventType.RED_CARD):
            cards[(e.player_id, e.type)] += 1
    for (_, kind), count in cards.items():
        limit = MAX_YELLOW_CARDS if kind == MatchEventType.YELLOW_CARD else MAX_RED_CARDS
        if count > limit:
            raise _bad(
                "A player can get at most two yellow cards in a match"
                if kind == MatchEventType.YELLOW_CARD
                else "A player can only be sent off once in a match"
            )

    goals = _goals_by_side(events, team_of, fixture)
    _check_goals_fit_score(goals, fixture, home_score, away_score, _team_names(db, fixture))

    return [
        MatchEvent(
            fixture_id=fixture.id, type=e.type, player_id=e.player_id,
            assist_player_id=e.assist_player_id, minute=e.minute,
        )
        for e in events
    ]


def check_recorded_events_fit(db: Session, fixture: Fixture, home_score: int, away_score: int) -> None:
    """A new score that keeps the recorded events must still cover their goals."""
    if not fixture.events:
        return
    team_of = {e.player_id: e.player.team_id for e in fixture.events}
    goals = _goals_by_side(fixture.events, team_of, fixture)
    _check_goals_fit_score(goals, fixture, home_score, away_score, _team_names(db, fixture))


def replace_events(fixture: Fixture, new_events: list[MatchEvent]) -> None:
    """Swap a fixture's events for a new set. Does NOT commit."""
    fixture.events.clear()
    fixture.events.extend(new_events)


# ---------------------------------------------------------------------------
# Leaderboards
# ---------------------------------------------------------------------------

def _ranked(rows: list[dict], key) -> list[dict]:
    """Standard competition ranking (1, 2, 2, 4): equal keys share a rank."""
    previous, rank = None, 0
    for i, row in enumerate(rows, start=1):
        k = key(row)
        if k != previous:
            rank, previous = i, k
        row["rank"] = rank
    return rows


def competition_stats(db: Session, competition: Competition, limit: int = 20) -> CompetitionStats:
    if not player_stats_supported(competition):
        return CompetitionStats(supported=False, scorers=[], assists=[], discipline=[])

    in_competition = Fixture.competition_id == competition.id
    goals = dict(
        db.query(MatchEvent.player_id, func.count())
        .join(Fixture, MatchEvent.fixture_id == Fixture.id)
        .filter(in_competition, MatchEvent.type == MatchEventType.GOAL)
        .group_by(MatchEvent.player_id)
        .all()
    )
    assists = dict(
        db.query(MatchEvent.assist_player_id, func.count())
        .join(Fixture, MatchEvent.fixture_id == Fixture.id)
        .filter(in_competition, MatchEvent.assist_player_id.isnot(None))
        .group_by(MatchEvent.assist_player_id)
        .all()
    )
    card_rows = (
        db.query(
            MatchEvent.player_id,
            func.sum(case((MatchEvent.type == MatchEventType.YELLOW_CARD, 1), else_=0)),
            func.sum(case((MatchEvent.type == MatchEventType.RED_CARD, 1), else_=0)),
        )
        .join(Fixture, MatchEvent.fixture_id == Fixture.id)
        .filter(in_competition, MatchEvent.type.in_([MatchEventType.YELLOW_CARD, MatchEventType.RED_CARD]))
        .group_by(MatchEvent.player_id)
        .all()
    )
    cards = {pid: (int(y or 0), int(r or 0)) for pid, y, r in card_rows}

    ids = set(goals) | set(assists) | set(cards)
    people = {
        p.id: (p, t)
        for p, t in db.query(Player, Team).join(Team, Player.team_id == Team.id).filter(Player.id.in_(ids)).all()
    } if ids else {}

    def row(pid: UUID, value: int) -> Optional[dict]:
        if pid not in people:
            return None
        p, t = people[pid]
        return {"player_id": p.id, "player_name": p.name, "shirt_number": p.shirt_number,
                "team_id": t.id, "team_name": t.name, "value": value}

    def board(counts: dict, tiebreak: dict) -> list[PlayerStatRow]:
        rows = [r for r in (row(pid, n) for pid, n in counts.items()) if r]
        # Most first; level players by the other stat, then name. Only the
        # headline number decides a shared rank.
        rows.sort(key=lambda r: (-r["value"], -tiebreak.get(r["player_id"], 0), r["player_name"].lower()))
        return [PlayerStatRow(**r) for r in _ranked(rows, key=lambda r: r["value"])[:limit]]

    discipline = []
    for pid, (yellow, red) in cards.items():
        r = row(pid, yellow + red)
        if r:
            discipline.append({**r, "yellow_cards": yellow, "red_cards": red})
    discipline.sort(key=lambda r: (-r["red_cards"], -r["yellow_cards"], r["player_name"].lower()))
    discipline = _ranked(discipline, key=lambda r: (r["red_cards"], r["yellow_cards"]))[:limit]

    return CompetitionStats(
        supported=True,
        scorers=board(goals, assists),
        assists=board(assists, goals),
        discipline=[DisciplineRow(**r) for r in discipline],
    )
