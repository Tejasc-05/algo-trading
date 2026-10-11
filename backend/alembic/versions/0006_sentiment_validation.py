"""Headline evidence and private validation annotations."""
from alembic import op
import sqlalchemy as sa
from app.database.models.base import JSONVariant
revision = '0006_sentiment_validation'
down_revision = '0005_binance_demo'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('sentiment_evidence',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('symbol', sa.String(8), nullable=False),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload', JSONVariant, nullable=False))
    op.create_table('sentiment_reviews',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('evidence_id', sa.String(64), sa.ForeignKey('sentiment_evidence.id', ondelete='CASCADE'), nullable=False),
        sa.Column('human_label', sa.String(16)),
        sa.Column('source_verdict', sa.String(16), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('user_id', 'evidence_id', name='uq_sentiment_review_owner_evidence'))
    op.create_index('ix_sentiment_reviews_user_id', 'sentiment_reviews', ['user_id'])


def downgrade():
    op.drop_table('sentiment_reviews')
    op.drop_table('sentiment_evidence')
