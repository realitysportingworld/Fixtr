"""
Everything the shared web page shows, as plain data for the template:
tables, the knockout bracket, every match by round, and top scorers. The
template only lays it out.
"""
from datetime import timezone
from itertools import groupby
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from app.models.models import (
    Competition, CompetitionFormat, CompetitionStatus, Fixture, FixtureStatus, Group, Team,
)
from app.services.knockout import tie_winner
from app.services.player_stats import competition_stats
from app.services.scoring import draws_allowed, ranking_mode
from app.services.standings import ranked_table

FORMAT_LABELS = {
    CompetitionFormat.LEAGUE: "League",
    CompetitionFormat.KNOCKOUT: "Knockout",
    CompetitionFormat.GROUP_KNOCKOUT: "Groups + Knockout",
    CompetitionFormat.LEAGUE_PHASE: "Champions League style",
}
STATUS_LABELS = {
    CompetitionStatus.DRAFT: "Getting ready",
    CompetitionStatus.ACTIVE: "In progress",
    CompetitionStatus.COMPLETED: "Finished",
    CompetitionStatus.CANCELLED: "Cancelled",
}
TOP_SCORERS = 10


def _kickoff(fixture: Fixture) -> Optional[dict]:
    if not fixture.scheduled_at:
        return None
    at = fixture.scheduled_at.replace(tzinfo=timezone.utc)
    # The page swaps this for the reader's own time zone; this is the fallback
    return {"iso": at.isoformat().replace("+00:00", "Z"), "text": f"{at:%a} {at.day} {at:%b} · {at:%H:%M} UTC"}


def _match(fixture: Fixture, name) -> dict:
    played = fixture.result is not None
    winner = None
    if played and fixture.result.winner_id:
        winner = "home" if fixture.result.winner_id == fixture.home_team_id else "away"
    return {
        "home": name(fixture.home_team_id),
        "away": name(fixture.away_team_id) if fixture.away_team_id else None,
        "home_score": fixture.result.home_score if played else None,
        "away_score": fixture.result.away_score if played else None,
        "played": played,
        "winner": winner,
        "postponed": fixture.status == FixtureStatus.POSTPONED,
        "kickoff": _kickoff(fixture),
        "leg": fixture.leg,
    }


def _tie(fixtures: list[Fixture], name) -> dict:
    """One bracket slot: a BYE, a single match, or two legs on aggregate."""
    deciding = next((f for f in fixtures if f.leg == 2), fixtures[0])
    winner_id = tie_winner(fixtures)
    tie = {
        "home": name(deciding.home_team_id),
        "away": name(deciding.away_team_id) if deciding.away_team_id else None,
        "bye": deciding.away_team_id is None,
        "winner": None,
        "legs": [_match(f, name) for f in sorted(fixtures, key=lambda f: f.leg or 0)],
        "aggregate": None,
    }
    if winner_id:
        tie["winner"] = "home" if winner_id == deciding.home_team_id else "away"
    first = next((f for f in fixtures if f.leg == 1), None)
    if first and first.result and deciding.result and deciding is not first:
        # Leg 2's home side was away in leg 1
        tie["aggregate"] = (
            deciding.result.home_score + first.result.away_score,
            deciding.result.away_score + first.result.home_score,
        )
    return tie


def _current_round(rounds: list[dict]) -> Optional[int]:
    """The round to show open: the first with a match still to play, else the last."""
    for r in rounds:
        if any(not m["played"] for m in r["matches"]):
            return r["number"]
    return rounds[-1]["number"] if rounds else None


def _headline(competition: Competition, tables: list[dict], bracket: list[dict], team_count: int) -> str:
    """One line for link previews: where it stands right now."""
    parts = [competition.sport.value.capitalize(), FORMAT_LABELS[competition.format], f"{team_count} teams"]
    final = bracket[-1]["ties"][0] if bracket and len(bracket[-1]["ties"]) == 1 else None
    if final and final["winner"]:
        parts.append(f"Winner: {final[final['winner']]}")
    elif tables and len(tables) == 1 and tables[0]["rows"] and tables[0]["rows"][0]["played"]:
        top = tables[0]["rows"][0]
        verb = "Champions" if competition.status == CompetitionStatus.COMPLETED else "Top"
        if tables[0]["win_pct"]:
            parts.append(f"{verb}: {top['team_name']} ({top['wins']}-{top['losses']})")
        else:
            parts.append(f"{verb}: {top['team_name']}, {top['points']} pts")
    return " · ".join(parts)


def build_share_view(db: Session, competition: Competition) -> dict:
    teams = db.query(Team).filter(Team.competition_id == competition.id).order_by(Team.name).all()
    names = {t.id: t.name for t in teams}
    name = lambda tid: names.get(tid, "Unknown")  # noqa: E731

    fixtures = (
        db.query(Fixture)
        .options(selectinload(Fixture.result))
        .filter(Fixture.competition_id == competition.id)
        .order_by(Fixture.round_number, Fixture.bracket_position, Fixture.leg, Fixture.created_at)
        .all()
    )

    win_pct = ranking_mode(competition) == "win_pct"
    table_common = {"win_pct": win_pct, "draws": draws_allowed(competition)}
    tables = []
    if not fixtures:
        pass  # before the draw there's no table, just the teams
    elif competition.format in (CompetitionFormat.LEAGUE, CompetitionFormat.LEAGUE_PHASE):
        rows = ranked_table(db, competition, teams)
        zones = {}
        if competition.format == CompetitionFormat.LEAGUE_PHASE:
            config = competition.format_config or {}
            direct, playoff = config.get("direct_qualifiers", 0), config.get("playoff_qualifiers", 0)
            zones = {"direct": direct, "playoff": direct + playoff}
        for i, r in enumerate(rows, start=1):
            r["position"] = i
            r["zone"] = ("direct" if i <= zones.get("direct", 0)
                         else "playoff" if i <= zones.get("playoff", 0) else None)
        tables.append({"title": None, "rows": rows, "zones": zones, **table_common})
    elif competition.format == CompetitionFormat.GROUP_KNOCKOUT:
        for group in db.query(Group).filter(Group.competition_id == competition.id).order_by(Group.name):
            rows = ranked_table(db, competition, [t for t in teams if t.group_id == group.id], group_id=group.id)
            for i, r in enumerate(rows, start=1):
                r["position"], r["zone"] = i, None
            tables.append({"title": group.name, "rows": rows, "zones": {}, **table_common})

    table_stage = [f for f in fixtures if f.knockout_round is None]
    rounds = [
        {"number": number, "label": f"Round {number}", "matches": [_match(f, name) for f in group]}
        for number, group in groupby(table_stage, key=lambda f: f.round_number)
    ]
    current = _current_round(rounds)
    for r in rounds:
        r["open"] = r["number"] == current

    knockout = [f for f in fixtures if f.knockout_round is not None]
    bracket = []
    for _, round_fixtures in groupby(knockout, key=lambda f: f.round_number):
        round_fixtures = list(round_fixtures)
        ties = [_tie(list(t), name) for _, t in groupby(round_fixtures, key=lambda f: f.bracket_position)]
        bracket.append({"label": round_fixtures[0].knockout_round, "ties": ties})

    stats = competition_stats(db, competition, limit=TOP_SCORERS)
    label = (competition.scoring_config or {}).get("score_label", "Score")

    return {
        "name": competition.name,
        "description": competition.description,
        "sport": competition.sport.value.capitalize(),
        "format": FORMAT_LABELS[competition.format],
        "status": competition.status.value,
        "status_label": STATUS_LABELS[competition.status],
        "organiser": competition.owner.username if competition.owner else None,
        "team_count": len(teams),
        "teams": [t.name for t in teams],
        "tables": tables,
        "rounds": rounds,
        "bracket": bracket,
        "scorers": [s.model_dump() for s in stats.scorers],
        "assists": [s.model_dump() for s in stats.assists[:5]],
        "score_label": label,
        "headline": _headline(competition, tables, bracket, len(teams)),
    }
