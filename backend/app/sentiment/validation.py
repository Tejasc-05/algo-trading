"""Persist observed evidence, isolated reviews, and descriptive classification metrics.

A first-seen timestamp starts at ingestion, never at the publisher's historical date.
Metrics are reviewer agreement, not a held-out benchmark or a trading evaluation.
"""
import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.database.models.sentiment import SentimentEvidence, SentimentReview

LABELS = ('positive', 'negative', 'neutral')


async def capture(db, user_id, result):
    insert = sqlite_insert if db.bind.dialect.name == 'sqlite' else pg_insert
    now = datetime.now(timezone.utc)
    for article in result.articles:
        payload = article.model_dump(mode='json')
        payload.update(provider=result.provider, model=result.model, model_revision=result.model_revision,
            inference_mode=result.inference_mode, computed_at=result.as_of.isoformat(), symbol=result.symbol)
        # Repeated polling cannot inflate the dataset; text/model changes produce new evidence.
        identity = {key: payload[key] for key in ('url', 'title', 'symbol', 'provider', 'model', 'model_revision', 'inference_mode')}
        evidence_id = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        await db.execute(insert(SentimentEvidence).values(id=evidence_id, symbol=result.symbol,
            first_seen_at=now, payload=payload).on_conflict_do_nothing())
        review_id = hashlib.sha256(f'{user_id}:{evidence_id}'.encode()).hexdigest()
        await db.execute(insert(SentimentReview).values(id=review_id, user_id=user_id,
            evidence_id=evidence_id, source_verdict='unverified', notes='').on_conflict_do_nothing())
    await db.commit()


def review_query(user_id, symbol=None):
    query = select(SentimentReview, SentimentEvidence).join(SentimentEvidence,
        SentimentReview.evidence_id == SentimentEvidence.id).where(SentimentReview.user_id == user_id)
    if symbol:
        query = query.where(SentimentEvidence.symbol == symbol)
    return query.order_by(SentimentEvidence.first_seen_at.desc(), SentimentReview.id)


def serialize(review, evidence, reveal=False):
    payload = dict(evidence.payload)
    if not reveal and review.human_label is None:
        for key in ('label', 'score', 'confidence', 'probabilities'):
            payload.pop(key, None)
    first_seen = evidence.first_seen_at
    if first_seen.tzinfo is None:  # SQLite's datetime roundtrip lacks a timezone.
        first_seen = first_seen.replace(tzinfo=timezone.utc)
    return dict(id=review.id, article=payload, first_seen_at=first_seen.isoformat(),
        human_label=review.human_label, source_verdict=review.source_verdict, notes=review.notes,
        reviewed_at=review.reviewed_at.isoformat() if review.reviewed_at else None)


async def metrics(db, user_id, symbol):
    # Group in SQL: metrics cover the complete dataset, independent of pagination.
    predicted_label = SentimentEvidence.payload['label'].as_string()
    query = select(SentimentReview.human_label, SentimentReview.source_verdict,
        predicted_label, func.count()).join(SentimentEvidence,
        SentimentReview.evidence_id == SentimentEvidence.id).where(
        SentimentReview.user_id == user_id, SentimentEvidence.symbol == symbol).group_by(
        SentimentReview.human_label, SentimentReview.source_verdict, predicted_label)
    matrix = {label: dict.fromkeys(LABELS, 0) for label in LABELS}
    total = reviewed = excluded = 0
    for human, verdict, predicted, count in (await db.execute(query)).all():
        total += count
        if human is not None:
            reviewed += count
        if human in LABELS and verdict == 'verified' and predicted in LABELS:
            matrix[human][predicted] += count
        elif human is not None:
            excluded += count
    evaluated = sum(sum(row.values()) for row in matrix.values())
    per_class = {}
    for label in LABELS:
        tp = matrix[label][label]
        support = sum(matrix[label].values())
        predictions = sum(matrix[actual][label] for actual in LABELS)
        precision = tp / predictions if predictions else 0.0
        recall = tp / support if support else 0.0
        per_class[label] = dict(precision=precision, recall=recall,
            f1=2*precision*recall/(precision+recall) if precision+recall else 0.0, support=support)
    return dict(total=total, reviewed=reviewed, evaluated=evaluated, excluded=excluded,
        accuracy=sum(matrix[label][label] for label in LABELS)/evaluated if evaluated else None,
        macro_f1=sum(row['f1'] for row in per_class.values())/3 if evaluated else None,
        per_class=per_class, confusion_matrix=matrix,
        interpretation='Verified-source reviewer agreement only. Not a held-out benchmark or evidence of trading profitability.')
