import random
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.models import (
    Competition, CompetitionFormat, CompetitionStatus,
    Fixture, FixtureStatus, Group, Result, Standing, Team, User,
)
from app.schemas.fixture import (
    AdvanceToKnockoutRequest, FixtureResponse, FixtureSchedule, ManualFixtureCreate,
)
from app.services.fixture_generator import (
    arrange_first_round, generate_round_robin, generate_knockout_bracket, num_byes,
)
from app.services.knockout import create_first_round
from app.services.standings import ranked_table

router = APIRouter()


def get_competition_or_404(competition_id: UUID, user: User, db: Session) -> Competition:
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.owner_id == user.id,
    ).first()
    if not competition:
        raise HTTPException(status_code=404, detail="Competition not found")
    return competition


def _build_fixtures(db: Session, competition: Competition, teams: list) -> list:
    """
    Create and add fixture (and Group) objects for the given competition.
    Does NOT commit — caller handles that.
    """
    fixtures = []
    team_ids = [str(t.id) for t in teams]

    if competition.format == CompetitionFormat.LEAGUE:
        rounds = generate_round_robin(team_ids)
        for round_number, matches in enumerate(rounds, start=1):
            for home_id, away_id in matches:
                f = Fixture(
                    competition_id=competition.id,
                    home_team_id=home_id,
                    away_team_id=away_id,
                    round_number=round_number,
                )
                db.add(f)
                fixtures.append(f)

    elif competition.format == CompetitionFormat.KNOCKOUT:
        # Only round 1 is created; later rounds are added by advance_knockout_round
        entries = generate_knockout_bracket(team_ids)
        fixtures.extend(create_first_round(db, competition.id, entries, round_number=1))

    elif competition.format == CompetitionFormat.GROUP_KNOCKOUT:
        if not competition.num_groups or competition.num_groups < 2:
            raise HTTPException(
                status_code=400,
                detail="num_groups must be at least 2 for group knockout format",
            )

        # Create groups (A, B, C, ...)
        groups = []
        for i in range(competition.num_groups):
            g = Group(competition_id=competition.id, name=f"Group {chr(65 + i)}")
            db.add(g)
            groups.append(g)
        db.flush()  # get group IDs before assigning teams

        # Assign teams to groups round-robin (team 0→A, 1→B, 2→C, 3→A, ...)
        for idx, team in enumerate(teams):
            team.group_id = groups[idx % competition.num_groups].id
        db.flush()

        # Round-robin within each group
        for group in groups:
            group_team_ids = [str(t.id) for t in teams if t.group_id == group.id]
            rounds = generate_round_robin(group_team_ids)
            for round_number, matches in enumerate(rounds, start=1):
                for home_id, away_id in matches:
                    f = Fixture(
                        competition_id=competition.id,
                        group_id=group.id,
                        home_team_id=home_id,
                        away_team_id=away_id,
                        round_number=round_number,
                    )
                    db.add(f)
                    fixtures.append(f)

    else:
        raise HTTPException(status_code=400, detail=f"Unknown format: {competition.format}")

    return fixtures


@router.post("/generate", response_model=list[FixtureResponse], status_code=status.HTTP_201_CREATED)
def generate_fixtures(
    competition_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    competition = get_competition_or_404(competition_id, current_user, db)

    if competition.status != CompetitionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Fixtures already generated for this competition")

    teams = db.query(Team).filter(Team.competition_id == competition_id).all()
    if len(teams) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 teams to generate fixtures")

    _build_fixtures(db, competition, teams)
    competition.status = CompetitionStatus.ACTIVE
    db.commit()

    return db.query(Fixture).filter(Fixture.competition_id == competition_id).all()


@router.post("/regenerate", response_model=list[FixtureResponse])
def regenerate_fixtures(
    competition_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Wipe all fixtures, results, standings and groups, then regenerate from scratch."""
    competition = get_competition_or_404(competition_id, current_user, db)

    if competition.status == CompetitionStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Cannot regenerate fixtures for a completed competition")

    teams = db.query(Team).filter(Team.competition_id == competition_id).all()
    if len(teams) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 teams to generate fixtures")

    # Delete children before parents: results → standings → fixtures → groups.
    # Bulk deletes bypass ORM cascades, so each table is cleared explicitly.
    fixture_ids = db.query(Fixture.id).filter(Fixture.competition_id == competition_id)
    db.query(Result).filter(Result.fixture_id.in_(fixture_ids)).delete(synchronize_session=False)
    db.query(Standing).filter(Standing.competition_id == competition_id).delete()
    db.query(Fixture).filter(Fixture.competition_id == competition_id).delete()
    db.query(Team).filter(Team.competition_id == competition_id).update({"group_id": None})
    db.query(Group).filter(Group.competition_id == competition_id).delete()
    db.expire_all()

    _build_fixtures(db, competition, teams)
    competition.status = CompetitionStatus.ACTIVE
    db.commit()

    return db.query(Fixture).filter(Fixture.competition_id == competition_id).all()


@router.post(
    "/advance-to-knockout",
    response_model=list[FixtureResponse],
    status_code=status.HTTP_201_CREATED,
)
def advance_to_knockout(
    competition_id: UUID,
    payload: AdvanceToKnockoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    After all group stage matches are complete, advance the top N teams from
    each group into a knockout bracket.
    """
    competition = get_competition_or_404(competition_id, current_user, db)

    if competition.format != CompetitionFormat.GROUP_KNOCKOUT:
        raise HTTPException(status_code=400, detail="Only GROUP_KNOCKOUT competitions support this")

    if competition.status != CompetitionStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Competition must be active")

    # Guard: knockout phase not already started
    existing_ko = db.query(Fixture).filter(
        Fixture.competition_id == competition_id,
        Fixture.knockout_round.isnot(None),
    ).first()
    if existing_ko:
        raise HTTPException(status_code=400, detail="Knockout phase already started")

    # Check all group fixtures are complete
    group_fixtures = db.query(Fixture).filter(
        Fixture.competition_id == competition_id,
        Fixture.group_id.isnot(None),
    ).all()

    if not group_fixtures:
        raise HTTPException(status_code=400, detail="No group stage fixtures found")

    incomplete = [f for f in group_fixtures if f.status != FixtureStatus.COMPLETED]
    if incomplete:
        raise HTTPException(
            status_code=400,
            detail=f"{len(incomplete)} group stage fixture(s) not yet complete",
        )

    # Determine top N per group using existing Standing rows
    groups = (
        db.query(Group)
        .filter(Group.competition_id == competition_id)
        .order_by(Group.name)
        .all()
    )

    # Collect top N per group, tracking which position (1st, 2nd, ...) each team finished
    position_buckets: list[list[tuple[str, str]]] = [[] for _ in range(payload.teams_per_group)]

    for group in groups:
        group_teams = db.query(Team).filter(Team.group_id == group.id).all()
        ranked = ranked_table(db, competition, group_teams, group_id=group.id)
        for pos, row in enumerate(ranked[: payload.teams_per_group]):
            position_buckets[pos].append((str(row["team_id"]), str(group.id)))

    # Seed order: all group winners, then all runners-up, etc. (random within
    # each position). Top seeds receive any BYEs needed to fill the bracket.
    seeded: list[tuple[str, str]] = []
    for bucket in position_buckets:
        bucket = list(bucket)
        random.shuffle(bucket)
        seeded.extend(bucket)

    if len(seeded) < 2:
        raise HTTPException(status_code=400, detail="Not enough teams to form a knockout bracket")

    byes = num_byes(len(seeded))
    bye_teams, playing = seeded[:byes], seeded[byes:]

    # Pair each remaining higher seed with the lowest remaining seed from a
    # different group, to avoid same-group first-round matchups where possible.
    matches: list[tuple[str, str]] = []
    while playing:
        home_id, home_group = playing.pop(0)
        candidates = [i for i, t in enumerate(playing) if t[1] != home_group] or list(range(len(playing)))
        away_id, _ = playing.pop(candidates[-1])
        matches.append((home_id, away_id))

    entries = arrange_first_round([t[0] for t in bye_teams], matches)

    # First knockout round starts after the last group stage round; later rounds
    # are created automatically by advance_knockout_round after each result
    ko_start_round = max(f.round_number for f in group_fixtures) + 1
    new_fixtures = create_first_round(db, competition_id, entries, round_number=ko_start_round)

    db.commit()
    for f in new_fixtures:
        db.refresh(f)
    return new_fixtures


@router.post("/manual", response_model=FixtureResponse, status_code=status.HTTP_201_CREATED)
def add_manual_fixture(
    competition_id: UUID,
    payload: ManualFixtureCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a single fixture manually. Activates the competition on first manual fixture."""
    competition = get_competition_or_404(competition_id, current_user, db)

    if competition.status == CompetitionStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Cannot add fixtures to a completed competition")

    if payload.home_team_id == payload.away_team_id:
        raise HTTPException(status_code=400, detail="Home and away teams must be different")

    teams = []
    for team_id in [payload.home_team_id, payload.away_team_id]:
        team = db.query(Team).filter(
            Team.id == team_id, Team.competition_id == competition_id
        ).first()
        if not team:
            raise HTTPException(status_code=400, detail=f"Team {team_id} not found in this competition")
        teams.append(team)

    # Group-stage matches must count towards a group table
    group_id = None
    if competition.format == CompetitionFormat.GROUP_KNOCKOUT:
        home, away = teams
        if home.group_id is None or home.group_id != away.group_id:
            raise HTTPException(
                status_code=400,
                detail="Manual fixtures in a group competition must be between teams in the same group",
            )
        group_id = home.group_id

    fixture = Fixture(
        competition_id=competition_id,
        group_id=group_id,
        home_team_id=payload.home_team_id,
        away_team_id=payload.away_team_id,
        round_number=payload.round_number,
    )
    db.add(fixture)

    if competition.status == CompetitionStatus.DRAFT:
        competition.status = CompetitionStatus.ACTIVE

    db.commit()
    db.refresh(fixture)
    return fixture


@router.delete("/{fixture_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fixture(
    competition_id: UUID,
    fixture_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a single fixture. Only allowed if the fixture has no result yet."""
    get_competition_or_404(competition_id, current_user, db)

    fixture = db.query(Fixture).filter(
        Fixture.id == fixture_id,
        Fixture.competition_id == competition_id,
    ).first()
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")
    if fixture.result:
        raise HTTPException(status_code=400, detail="Cannot delete a fixture that already has a result")
    if fixture.knockout_round:
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a knockout fixture; regenerate fixtures to rebuild the bracket",
        )

    db.delete(fixture)
    db.commit()


@router.get("/", response_model=list[FixtureResponse])
def list_fixtures(
    competition_id: UUID,
    round_number: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    get_competition_or_404(competition_id, current_user, db)
    query = db.query(Fixture).filter(Fixture.competition_id == competition_id)
    if round_number is not None:
        query = query.filter(Fixture.round_number == round_number)
    return query.order_by(Fixture.round_number, Fixture.bracket_position, Fixture.created_at).all()


@router.patch("/schedule", status_code=status.HTTP_200_OK)
def schedule_fixtures(
    competition_id: UUID,
    schedules: list[FixtureSchedule],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Set scheduled_at datetime for one or more fixtures."""
    get_competition_or_404(competition_id, current_user, db)

    for s in schedules:
        fixture = db.query(Fixture).filter(
            Fixture.id == s.fixture_id,
            Fixture.competition_id == competition_id,
        ).first()
        if fixture:
            fixture.scheduled_at = s.scheduled_at

    db.commit()
    return {"updated": len(schedules)}
