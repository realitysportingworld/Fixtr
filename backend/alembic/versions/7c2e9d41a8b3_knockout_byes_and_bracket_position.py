"""knockout byes and bracket position

Revision ID: 7c2e9d41a8b3
Revises: 59a671593911
Create Date: 2026-10-20 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c2e9d41a8b3'
down_revision: Union[str, Sequence[str], None] = '59a671593911'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column('fixtures', 'away_team_id', existing_type=sa.UUID(), nullable=True)
    op.add_column('fixtures', sa.Column('bracket_position', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('fixtures', 'bracket_position')
    op.execute("DELETE FROM fixtures WHERE away_team_id IS NULL")
    op.alter_column('fixtures', 'away_team_id', existing_type=sa.UUID(), nullable=False)
