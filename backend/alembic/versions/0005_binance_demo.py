"""Durable Binance demo sessions and order intents."""
from alembic import op
import sqlalchemy as sa
from app.database.models.base import JSONVariant

revision = '0005_binance_demo'
down_revision = '0004_enum_defaults'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('futures_demo_sessions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('connection_id', sa.String(36), sa.ForeignKey('exchange_connections.id'), nullable=False),
        sa.Column('strategy_version_id', sa.String(36), sa.ForeignKey('strategy_versions.id'), nullable=False),
        sa.Column('symbol', sa.String(16), nullable=False), sa.Column('timeframe', sa.String(8), nullable=False),
        sa.Column('status', sa.String(24), nullable=False),
        sa.Column('max_notional', sa.Numeric(20,8), nullable=False), sa.Column('loss_limit', sa.Numeric(20,8), nullable=False),
        sa.Column('starting_equity', sa.Numeric(20,8), nullable=False), sa.Column('last_bar', sa.String(40)),
        sa.Column('lease_owner', sa.String(36)), sa.Column('lease_until', sa.DateTime(timezone=True)),
        sa.Column('message', sa.String(255)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index('ix_futures_demo_sessions_user_id', 'futures_demo_sessions', ['user_id'])
    op.create_index('uq_demo_active_connection', 'futures_demo_sessions', ['connection_id'], unique=True,
        postgresql_where=sa.text("status != 'stopped'"), sqlite_where=sa.text("status != 'stopped'"))
    op.create_table('futures_demo_orders',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('session_id', sa.String(36), sa.ForeignKey('futures_demo_sessions.id'), nullable=False),
        sa.Column('client_id', sa.String(36), nullable=False), sa.Column('role', sa.String(16), nullable=False),
        sa.Column('state', sa.String(24), nullable=False), sa.Column('params', JSONVariant, nullable=False),
        sa.Column('result', JSONVariant),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('client_id', name='uq_demo_client_id'))
    op.create_index('ix_futures_demo_orders_session_id', 'futures_demo_orders', ['session_id'])


def downgrade():
    op.drop_table('futures_demo_orders')
    op.drop_table('futures_demo_sessions')
