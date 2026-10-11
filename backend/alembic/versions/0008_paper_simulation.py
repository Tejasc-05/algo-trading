"""Paper controls, isolated futures balances, diagnostics and equity history."""
from alembic import op
import sqlalchemy as sa
from app.database.models.base import JSONVariant
revision = '0008_paper_simulation'
down_revision = '0007_futures_diagnostics'
branch_labels = None
depends_on = None


def upgrade():
    for name, typ, default in [
        ('market_type', sa.String(16), 'spot'), ('leverage', sa.Integer(), '1'),
        ('fee_rate', sa.Numeric(12, 8), '0.001'), ('slippage_rate', sa.Numeric(12, 8), '0.0005'),
        ('maintenance_margin_rate', sa.Numeric(12, 8), '0.005'), ('funding_rate', sa.Numeric(12, 8), '0.0001')]:
        op.add_column('paper_accounts', sa.Column(name, typ, server_default=default, nullable=False))
    op.add_column('paper_accounts', sa.Column('diagnostics', JSONVariant, nullable=True))
    op.add_column('orders', sa.Column('risk_params', JSONVariant, nullable=True))
    for name in ['margin_balance', 'entry_fee', 'funding_paid']:
        op.add_column('positions', sa.Column(name, sa.Numeric(20, 8), server_default='0', nullable=False))
    op.add_column('positions', sa.Column('last_funding_at', sa.DateTime(timezone=True), nullable=True))
    op.create_table('paper_equity_snapshots',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('paper_account_id', sa.String(36), sa.ForeignKey('paper_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('equity', sa.Numeric(20, 8), nullable=False))
    op.create_index('ix_paper_equity_snapshots_paper_account_id', 'paper_equity_snapshots', ['paper_account_id'])


def downgrade():
    op.drop_table('paper_equity_snapshots')
    op.drop_column('orders', 'risk_params')
    for name in ['last_funding_at', 'funding_paid', 'entry_fee', 'margin_balance']:
        op.drop_column('positions', name)
    for name in ['diagnostics', 'funding_rate', 'maintenance_margin_rate', 'slippage_rate', 'fee_rate', 'leverage', 'market_type']:
        op.drop_column('paper_accounts', name)
