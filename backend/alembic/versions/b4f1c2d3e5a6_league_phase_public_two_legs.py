"""league phase format, public competitions, two-legged ties

Revision ID: b4f1c2d3e5a6
Revises: 7c2e9d41a8b3
Create Date: 2026-10-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4f1c2d3e5a6'
down_revision: Union[str, None] = '7c2e9d41a8b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLAlchemy stores enum member names, so the label is upper case
    op.execute("ALTER TYPE competitionformat ADD VALUE IF NOT EXISTS 'LEAGUE_PHASE'")
    op.add_column('competitions', sa.Column('format_config', sa.JSON(), nullable=True))
    op.add_column('competitions', sa.Column('is_public', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index('ix_competitions_is_public', 'competitions', ['is_public'])
    op.add_column('fixtures', sa.Column('leg', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('fixtures', 'leg')
    op.drop_index('ix_competitions_is_public', table_name='competitions')
    op.drop_column('competitions', 'is_public')
    op.drop_column('competitions', 'format_config')
    # Postgres can't drop a single enum value, so LEAGUE_PHASE stays in the type
