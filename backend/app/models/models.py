import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, String, JSON, UniqueConstraint, false
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.db.base import Base


def utcnow() -> datetime:
    """Current time as naive UTC, the convention for every DateTime column here."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CompetitionFormat(str, enum.Enum):
    LEAGUE = "league"                      # Round-robin, everyone plays everyone
    KNOCKOUT = "knockout"                  # Single elimination bracket
    GROUP_KNOCKOUT = "group_knockout"      # Group stage + knockout
    LEAGUE_PHASE = "league_phase"          # UCL-style: one table, N matches each, then play-off + knockout


class SportType(str, enum.Enum):
    FOOTBALL = "football"
    BASKETBALL = "basketball"
    RUGBY = "rugby"
    GOLF = "golf"
    VOLLEYBALL = "volleyball"
    CUSTOM = "custom"


class CompetitionStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MatchEventType(str, enum.Enum):
    GOAL = "goal"
    OWN_GOAL = "own_goal"            # credited to the other side
    YELLOW_CARD = "yellow_card"
    RED_CARD = "red_card"


class FixtureStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    POSTPONED = "postponed"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_premium = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    competitions = relationship("Competition", back_populates="owner")


class Competition(Base):
    __tablename__ = "competitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    format = Column(Enum(CompetitionFormat), nullable=False)
    sport = Column(Enum(SportType), nullable=False)
    status = Column(Enum(CompetitionStatus), default=CompetitionStatus.DRAFT)

    # For group stage: how many groups, teams per group
    num_groups = Column(Integer, nullable=True)

    # Scoring rules stored as JSON to support different sports
    # e.g. {"win": 3, "draw": 1, "loss": 0} for football
    scoring_config = Column(JSON, nullable=True)

    # Format options fixed at creation, e.g. {"two_legged": true} or, for
    # LEAGUE_PHASE, {"matches_per_team": 8, "direct_qualifiers": 8, "playoff_qualifiers": 16}
    format_config = Column(JSON, nullable=True)

    # Public competitions can be found and viewed (read-only) by other users
    is_public = Column(Boolean, nullable=False, default=False, server_default=false())

    # Unguessable code for the read-only web page at /c/{share_code}, which
    # works without an account. Null = link sharing off; a new code revokes the old link.
    share_code = Column(String(32), nullable=True, unique=True, index=True)

    max_participants = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    owner = relationship("User", back_populates="competitions")
    teams = relationship("Team", back_populates="competition", cascade="all, delete-orphan")
    groups = relationship("Group", back_populates="competition", cascade="all, delete-orphan")
    fixtures = relationship("Fixture", back_populates="competition", cascade="all, delete-orphan")

    @property
    def owner_username(self):
        return self.owner.username if self.owner else None


class Team(Base):
    __tablename__ = "teams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id"), nullable=False)
    name = Column(String, nullable=False)
    group_id = Column(UUID(as_uuid=True), ForeignKey("groups.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("competition_id", "name", name="uq_team_name_per_competition"),
    )

    competition = relationship("Competition", back_populates="teams")
    group = relationship("Group", back_populates="teams")
    players = relationship("Player", back_populates="team", cascade="all, delete-orphan")
    home_fixtures = relationship("Fixture", foreign_keys="Fixture.home_team_id", back_populates="home_team")
    away_fixtures = relationship("Fixture", foreign_keys="Fixture.away_team_id", back_populates="away_team")


class Group(Base):
    """Used for GROUP_KNOCKOUT format competitions."""
    __tablename__ = "groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id"), nullable=False)
    name = Column(String, nullable=False)  # e.g. "Group A", "Group B"

    competition = relationship("Competition", back_populates="groups")
    teams = relationship("Team", back_populates="group")
    fixtures = relationship("Fixture", back_populates="group")


class Fixture(Base):
    __tablename__ = "fixtures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id"), nullable=False)
    group_id = Column(UUID(as_uuid=True), ForeignKey("groups.id"), nullable=True)

    home_team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    # null = knockout BYE (home team auto-advances)
    away_team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)

    round_number = Column(Integer, nullable=False)
    scheduled_at = Column(DateTime, nullable=True)
    status = Column(Enum(FixtureStatus), default=FixtureStatus.SCHEDULED)

    # Knockout stage metadata
    knockout_round = Column(String, nullable=True)  # e.g. "QF", "SF", "F"
    # Position within the knockout round; winners of 0 & 1 meet next round, etc.
    bracket_position = Column(Integer, nullable=True)
    # Two-legged knockout ties: 1 or 2 (both legs share round and bracket_position).
    # null = a single match.
    leg = Column(Integer, nullable=True)

    created_at = Column(DateTime, default=utcnow)

    competition = relationship("Competition", back_populates="fixtures")
    group = relationship("Group", back_populates="fixtures")
    home_team = relationship("Team", foreign_keys=[home_team_id], back_populates="home_fixtures")
    away_team = relationship("Team", foreign_keys=[away_team_id], back_populates="away_fixtures")
    result = relationship("Result", back_populates="fixture", uselist=False, cascade="all, delete-orphan")
    events = relationship("MatchEvent", back_populates="fixture", cascade="all, delete-orphan",
                          order_by=lambda: (MatchEvent.minute.nulls_last(), MatchEvent.created_at))

    @property
    def is_bye(self):
        return self.knockout_round is not None and self.away_team_id is None

    @property
    def home_score(self):
        return self.result.home_score if self.result else None

    @property
    def away_score(self):
        return self.result.away_score if self.result else None

    @property
    def winner_id(self):
        return self.result.winner_id if self.result else None


class Result(Base):
    __tablename__ = "results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fixture_id = Column(UUID(as_uuid=True), ForeignKey("fixtures.id"), unique=True, nullable=False)

    home_score = Column(Integer, nullable=False)
    away_score = Column(Integer, nullable=False)

    # Extra sport-specific data (e.g. tries, bonus points, golf strokes per hole)
    extra_data = Column(JSON, nullable=True)

    winner_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=True)  # null = draw
    recorded_at = Column(DateTime, default=utcnow)

    fixture = relationship("Fixture", back_populates="result")
    winner = relationship("Team")


class Player(Base):
    """A squad member, so goals, assists and cards can be credited to someone."""
    __tablename__ = "players"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    shirt_number = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("team_id", "name", name="uq_player_name_per_team"),
        # NULLs don't collide, so players without a number are fine
        UniqueConstraint("team_id", "shirt_number", name="uq_player_number_per_team"),
    )

    team = relationship("Team", back_populates="players")


class MatchEvent(Base):
    """
    Something a player did in a match: a goal (optionally with an assist), an
    own goal, or a card. Only played matches have events; clearing the result
    removes them.
    """
    __tablename__ = "match_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fixture_id = Column(UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(Enum(MatchEventType), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False, index=True)
    assist_player_id = Column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=True, index=True)
    minute = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    fixture = relationship("Fixture", back_populates="events")
    player = relationship("Player", foreign_keys=[player_id])
    assist_player = relationship("Player", foreign_keys=[assist_player_id])


class Standing(Base):
    """Materialised standing row — recalculated after each result."""
    __tablename__ = "standings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    competition_id = Column(UUID(as_uuid=True), ForeignKey("competitions.id"), nullable=False)
    group_id = Column(UUID(as_uuid=True), ForeignKey("groups.id"), nullable=True)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)

    played = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    goals_for = Column(Integer, default=0)
    goals_against = Column(Integer, default=0)
    points = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("competition_id", "team_id", name="uq_standing_per_competition_team"),
    )
