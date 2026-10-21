"""Unique exchange-derived identity for production account verification."""
from alembic import op
import sqlalchemy as sa

revision = '0012_live_accounts'
down_revision = '0011_account_security'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('live_accounts',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('account_identity', sa.String(64), nullable=False, unique=True),
        sa.Column('connection_id', sa.String(36), sa.ForeignKey('exchange_connections.id', ondelete='SET NULL'), unique=True),
        sa.Column('verified_at', sa.DateTime(timezone=True)))
    op.create_index('ix_live_accounts_user_id', 'live_accounts', ['user_id'])


def downgrade():
    op.drop_table('live_accounts')
