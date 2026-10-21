"""Account-fenced durable intents. No production execution is enabled."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0013_live_order_ledger'
down_revision = '0012_live_accounts'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('live_accounts', sa.Column('fence_token', sa.String(36)))
    op.create_table('live_runs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(36), sa.ForeignKey('live_accounts.id'), nullable=False),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('strategy_version_id', sa.String(36), sa.ForeignKey('strategy_versions.id'), nullable=False),
        sa.Column('symbol', sa.String(16), nullable=False),
        sa.Column('timeframe', sa.String(8), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('policy', JSONB(), nullable=False),
        sa.Column('active_entry_id', sa.String(36)),
        sa.Column('last_bar', sa.String(40)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status != 'stopped' OR active_entry_id IS NULL", name='stopped_without_cycle'))
    op.create_index('ix_live_runs_account_id', 'live_runs', ['account_id'])
    op.create_index('ix_live_runs_user_id', 'live_runs', ['user_id'])
    op.create_index('uq_live_active_account', 'live_runs', ['account_id'], unique=True, postgresql_where=sa.text("status != 'stopped'"))
    op.create_table('live_orders',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(36), sa.ForeignKey('live_accounts.id'), nullable=False),
        sa.Column('run_id', sa.String(36), sa.ForeignKey('live_runs.id'), nullable=False),
        sa.Column('cycle_entry_id', sa.String(36), nullable=False),
        sa.Column('client_id', sa.String(36), unique=True, nullable=False),
        sa.Column('intent_key', sa.String(256), nullable=False),
        sa.Column('role', sa.String(12), nullable=False),
        sa.Column('state', sa.String(24), nullable=False),
        sa.Column('params', JSONB(), nullable=False),
        sa.Column('result', JSONB()),
        sa.Column('filled_quantity', sa.Numeric(28, 12), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('account_id', 'intent_key', name='uq_live_account_intent'))
    op.create_index('ix_live_orders_account_id', 'live_orders', ['account_id'])
    op.create_index('ix_live_orders_run_id', 'live_orders', ['run_id'])
    op.create_table('live_events',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('account_id', sa.String(36), sa.ForeignKey('live_accounts.id'), nullable=False),
        sa.Column('order_id', sa.String(36), sa.ForeignKey('live_orders.id')),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('detail', JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_live_events_account_id', 'live_events', ['account_id'])


def downgrade():
    op.drop_table('live_events')
    op.drop_table('live_orders')
    op.drop_table('live_runs')
    op.drop_column('live_accounts', 'fence_token')
