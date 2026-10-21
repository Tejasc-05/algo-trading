"""Revocable HttpOnly browser sessions."""
from alembic import op
import sqlalchemy as sa

revision = '0010_browser_sessions'
down_revision = '0009_password_reset'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('browser_sessions',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('auth_version', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.Column('mfa_at', sa.DateTime(timezone=True)))
    op.create_index('ix_browser_sessions_user_id', 'browser_sessions', ['user_id'])


def downgrade():
    op.drop_table('browser_sessions')
