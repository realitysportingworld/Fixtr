"""auth sessions with refresh tokens, password reset codes, shared rate limits

Revision ID: e5c7a9d1f402
Revises: d8a3f6b2c901
Create Date: 2026-11-16

Existing access tokens don't name a session, so everyone signs in once more
after this upgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5c7a9d1f402'
down_revision: Union[str, None] = 'd8a3f6b2c901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'auth_sessions',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('previous_token_hash', sa.String(length=64), nullable=True),
        sa.Column('rotated_at', sa.DateTime(), nullable=True),
        sa.Column('user_agent', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('last_used_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('token_hash', name='uq_auth_sessions_token_hash'),
    )
    op.create_index('ix_auth_sessions_user_id', 'auth_sessions', ['user_id'])
    op.create_index('ix_auth_sessions_previous_token_hash', 'auth_sessions', ['previous_token_hash'])

    op.create_table(
        'password_resets',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_password_resets_user_id', 'password_resets', ['user_id'])

    op.create_table(
        'rate_limit_events',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_rate_limit_events_created_at', 'rate_limit_events', ['created_at'])
    op.create_index('ix_rate_limit_events_key_created', 'rate_limit_events', ['key', 'created_at'])


def downgrade() -> None:
    op.drop_table('rate_limit_events')
    op.drop_table('password_resets')
    op.drop_table('auth_sessions')
