"""Verified-email state and encrypted authenticator enrollment."""
from alembic import op
import sqlalchemy as sa

revision = '0011_account_security'
down_revision = '0010_browser_sessions'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('account_security',
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('email_verified_at', sa.DateTime(timezone=True)),
        sa.Column('mfa_secret_encrypted', sa.Text()),
        sa.Column('pending_secret_encrypted', sa.Text()),
        sa.Column('pending_expires_at', sa.DateTime(timezone=True)),
        sa.Column('last_mfa_counter', sa.Integer(), server_default='-1', nullable=False))
    op.create_table('email_verification_tokens',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('auth_version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True)))
    op.create_index('ix_email_verification_tokens_user_id', 'email_verification_tokens', ['user_id'])


def downgrade():
    op.drop_table('email_verification_tokens')
    op.drop_table('account_security')
