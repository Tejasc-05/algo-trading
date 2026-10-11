"""Persist read-only explanation snapshots from the demo runner."""
from alembic import op
import sqlalchemy as sa
from app.database.models.base import JSONVariant
revision = '0007_futures_diagnostics'
down_revision = '0006_sentiment_validation'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('futures_demo_sessions', sa.Column('diagnostics', JSONVariant, nullable=True))


def downgrade():
    op.drop_column('futures_demo_sessions', 'diagnostics')
