import random
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.base import get_db
from app.models.models import (
    Competition, CompetitionFormat, CompetitionStatus,
    Fixture, FixtureStatus, Group, Standing, Team, User,
)
from app.schemas.fixture import (
    AdvanceToKnockoutRequest, FixtureResponse, FixtureSchedule, ManualFixtureCreate,
)
from app.services.fixture_generator import (
    generate_round_robin, generate_knockout_bracket, get_knockout_round_label,
)

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
        rounds = generate_knockout_bracket(team_ids)
        total_teams = len(team_ids)
        for round_number, matches in enumerate(rounds, start=1):
            label = get_knockout_round_label(total_teams // (2 ** (round_number - 1)))
            for home_id, away_id in matches:
                if home_id is None and away_id is None:
                    continue  # TBD — created dynamically after each round
                f = Fixture(
                    competition_id=competition.id,
                    home_team_id=home_id,
                    away_team_id=away_id,
                    round_number=round_number,
                    knockout_round=label,
                )
                db.add(f)
                fixtures.append(f)

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

    # For GROUP_KNOCKOUT: clear team group assignments before deleting groups
    if competition.format == CompetitionFormat.GROUP_KNOCKOUT:
        db.query(Team).filter(Team.competition_id == competition_id).update({"group_id": None})
        db.flush()
        db.query(Group).filter(Group.competition_id == competition_id).delete()
        db.flush()

    db.query(Standing).filter(Standing.competition_id == competition_id).delete()
    db.query(Fixture).filter(Fixture.competition_id == competition_id).delete()
    competition.status = CompetitionStatus.DRAFT
    db.commit()

    teams = db.query(Team).filter(Team.competition_id == competition_id).all()
    if len(teams) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 teams to generate fixtures")

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
        standings_rows = db.query(Standing).filter(
            Standing.competition_id == competition_id,
            Standing.group_id == group.id,
        ).all()
        standings_map = {s.team_id: s for s in standings_rows}

        ranked = []
        for team in group_teams:
            s = standings_map.get(team.id)
            pts = s.points if s else 0
            gd = (s.goals_for - s.goals_against) if s else 0
            gf = s.goals_for if s else 0
            ranked.append((str(team.id), pts, gd, gf))

        ranked.sort(key=lambda x: (-x[1], -x[2], -x[3]))
        for pos, (team_id, *_) in enumerate(ranked[: payload.teams_per_group]):
            position_buckets[pos].append((team_id, str(group.id)))

    total_advancing = sum(len(b) for b in position_buckets)
    if total_advancing < 2:
        raise HTTPException(status_code=400, detail="Not enough teams to form a knockout bracket")

    # Cross-seed: pair 1st-place finishers vs 2nd-place finishers from different groups.
    # Randomise each bucket, then greedily match each winner with a runner-up from a
    # different group to avoid same-group first-round matchups.
    winners = list(position_buckets[0])
    runners_up = list(position_buckets[1]) if len(position_buckets) > 1 else []

    random.shuffle(winners)
    random.shuffle(runners_up)

    advancing_team_ids: list[str] = []

    if runners_up:
        remaining_ru = list(runners_up)
        for winner_id, winner_group in winners:
            valid = [(i, r) for i, r in enumerate(remaining_ru) if r[1] != winner_group]
            if not valid:
                valid = list(enumerate(remaining_ru))  # fallback — take any
            chosen_idx, (chosen_id, _) = random.choice(valid)
            remaining_ru.pop(chosen_idx)
            advancing_team_ids.append(winner_id)
            advancing_team_ids.append(chosen_id)
        # Any leftover teams from extra positions (3rd-place playoff etc.)
        for pos in range(2, len(position_buckets)):
            advancing_team_ids.extend(t[0] for t in position_buckets[pos])
    else:
        # Only one advancing position — just shuffle winners directly
        advancing_team_ids = [t[0] for t in winners]

    # First knockout round starts after the last group stage round
    max_group_round = max(f.round_number for f in group_fixtures)
    ko_start_round = max_group_round + 1

    # Only create round-1 knockout fixtures (TBD rounds are skipped; later rounds
    # are created automatically by advance_knockout_round after each result)
    rounds = generate_knockout_bracket(advancing_team_ids)
    total = len(advancing_team_ids)

    new_fixtures = []
    for round_offset, matches in enumerate(rounds):
        round_number = ko_start_round + round_offset
        label = get_knockout_round_label(total // (2 ** round_offset))
        for home_id, away_id in matches:
            if home_id is None and away_id is None:
                continue
            f = Fixture(
                competition_id=competition_id,
                home_team_id=home_id,
                away_team_id=away_id,
                round_number=round_number,
                knockout_round=label,
            )
            db.add(f)
            new_fixtures.append(f)

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

    for team_id in [payload.home_team_id, payload.away_team_id]:
        team = db.query(Team).filter(
            Team.id == team_id, Team.competition_id == competition_id
        ).first()
        if not team:
            raise HTTPException(status_code=400, detail=f"Team {team_id} not found in this competition")

    fixture = Fixture(
        competition_id=competition_id,
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
    return query.order_by(Fixture.round_number).all()


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
