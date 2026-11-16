"""players, match events (goals, assists, cards), share links

Revision ID: d8a3f6b2c901
Revises: b4f1c2d3e5a6
Create Date: 2026-11-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'd8a3f6b2c901'
down_revision: Union[str, None] = 'b4f1c2d3e5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# SQLAlchemy stores enum member names, so the labels are upper case
event_type = postgresql.ENUM('GOAL', 'OWN_GOAL', 'YELLOW_CARD', 'RED_CARD', name='matcheventtype')


def upgrade() -> None:
    op.add_column('competitions', sa.Column('share_code', sa.String(length=32), nullable=True))
    op.create_index('ix_competitions_share_code', 'competitions', ['share_code'], unique=True)

    op.create_table(
        'players',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('team_id', sa.UUID(), sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('shirt_number', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('team_id', 'name', name='uq_player_name_per_team'),
        sa.UniqueConstraint('team_id', 'shirt_number', name='uq_player_number_per_team'),
    )
    op.create_index('ix_players_team_id', 'players', ['team_id'])

    op.create_table(
        'match_events',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('fixture_id', sa.UUID(), sa.ForeignKey('fixtures.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', event_type, nullable=False),
        sa.Column('player_id', sa.UUID(), sa.ForeignKey('players.id'), nullable=False),
        sa.Column('assist_player_id', sa.UUID(), sa.ForeignKey('players.id'), nullable=True),
        sa.Column('minute', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_match_events_fixture_id', 'match_events', ['fixture_id'])
    op.create_index('ix_match_events_player_id', 'match_events', ['player_id'])
    op.create_index('ix_match_events_assist_player_id', 'match_events', ['assist_player_id'])


def downgrade() -> None:
    op.drop_table('match_events')
    event_type.drop(op.get_bind(), checkfirst=True)
    op.drop_index('ix_players_team_id', table_name='players')
    op.drop_table('players')
    op.drop_index('ix_competitions_share_code', table_name='competitions')
    op.drop_column('competitions', 'share_code')
