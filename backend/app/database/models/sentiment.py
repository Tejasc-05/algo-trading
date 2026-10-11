"""Immutable public headline evidence and private reviewer annotations."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database.models.base import Base, JSONVariant


class SentimentEvidence(Base):
    __tablename__ = 'sentiment_evidence'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(8), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONVariant, nullable=False)


class SentimentReview(Base):
    __tablename__ = 'sentiment_reviews'
    __table_args__ = (UniqueConstraint('user_id', 'evidence_id', name='uq_sentiment_review_owner_evidence'),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    evidence_id: Mapped[str] = mapped_column(ForeignKey('sentiment_evidence.id', ondelete='CASCADE'), nullable=False)
    human_label: Mapped[str | None] = mapped_column(String(16))
    source_verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
