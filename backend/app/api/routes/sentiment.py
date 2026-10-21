"""Shared public news evidence and authenticated, user-owned validation reviews."""
import asyncio
import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy import select
from dataclasses import asdict
from fastapi import APIRouter, Depends, Query
from redis.exceptions import RedisError
from app.api.dependencies import get_current_user, get_redis, get_db
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.schemas.sentiment import SentimentOut, ReviewInput
from app.database.models.sentiment import SentimentReview, SentimentEvidence
from app.sentiment.validation import capture, review_query, serialize, metrics
from app.sentiment.rss import FEEDS
from app.sentiment.news_selection import POLICY, aggregate_news
from app.sentiment.quality import check_sample
from app.sentiment.providers import get_sentiment_provider, normalize_symbol
from app.sentiment.local_model import local_model_ready, REVISION

router = APIRouter(prefix='/sentiment', tags=['sentiment'])
_locks = {symbol: asyncio.Lock() for symbol in ('BTC', 'ETH')}


@router.get('/status')
async def sentiment_status(user=Depends(get_current_user)):
    settings = get_settings()
    return {'provider': settings.sentiment_news_provider, 'model': 'ProsusAI/finbert',
        'news_configured': settings.sentiment_news_provider == 'rss' or bool(settings.newsapi_api_key),
        'model_configured': local_model_ready() if settings.sentiment_inference_mode == 'local' else bool(settings.hf_token),
        'inference_mode': settings.sentiment_inference_mode,
        'supported_symbols': ['BTC', 'ETH'], 'feed_delay_hours': 0 if settings.sentiment_news_provider == 'rss' else settings.newsapi_delay_hours, 'trading_integration_enabled': False}


@router.get('/health/{symbol}')
async def source_health(symbol: str, user=Depends(get_current_user), redis=Depends(get_redis)):
    symbol = normalize_symbol(symbol)
    if get_settings().sentiment_news_provider != 'rss':
        return {'sources': [], 'message': 'Per-publisher health is available for RSS only.'}
    try:
        cached = await redis.get(f'sentiment:health:rss:{symbol}')
        if cached:
            retained = {item['source']: item for item in json.loads(cached)}
            sources = [retained[name] if name in retained and retained[name].get('feed_url') == url else
                {'source':name, 'feed_url':url, 'status':'unknown', 'checked_at':None,
                 'matching_headlines':None, 'newest_published_at':None} for name,url in FEEDS.items()]
            return {'sources': sources, 'message': 'Reachability does not verify article claims. Checks run when the news cache refreshes.'}
    except (RedisError, ValueError):
        pass
    return {'sources': [{'source': name, 'feed_url': url, 'status': 'unknown', 'checked_at': None,
        'matching_headlines': None, 'newest_published_at': None} for name, url in FEEDS.items()],
        'message': 'No retained health check. Refresh sentiment to check feeds.'}


@router.get('/reviews/{symbol}')
async def list_reviews(symbol: str, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    user=Depends(get_current_user), db=Depends(get_db)):
    symbol = normalize_symbol(symbol)
    rows = (await db.execute(review_query(user.id, symbol).offset(offset).limit(limit))).all()
    report = await metrics(db, user.id, symbol)
    return {'items': [serialize(review, evidence) for review, evidence in rows], 'metrics': report}


@router.put('/reviews/item/{review_id}')
async def save_review(review_id: str, body: ReviewInput, user=Depends(get_current_user), db=Depends(get_db)):
    review = await db.scalar(select(SentimentReview).where(SentimentReview.id == review_id, SentimentReview.user_id == user.id))
    if review is None:
        raise AppError('NOT_FOUND', 'Review not found', 404)
    review.human_label = body.human_label
    review.source_verdict = body.source_verdict
    review.notes = body.notes
    review.reviewed_at = datetime.now(timezone.utc)
    await db.commit()
    evidence = await db.get(SentimentEvidence, review.evidence_id)
    return serialize(review, evidence)


@router.get('/export/{symbol}')
async def export_reviews(symbol: str, offset: int = Query(0, ge=0), limit: int = Query(1000, ge=1, le=1000),
    user=Depends(get_current_user), db=Depends(get_db)):
    symbol = normalize_symbol(symbol)
    rows = (await db.execute(review_query(user.id, symbol).offset(offset).limit(limit))).all()
    report = await metrics(db, user.id, symbol)
    return {'schema_version': 1, 'symbol': symbol, 'metrics': report,
        'offset': offset, 'next_offset': offset + len(rows) if offset + len(rows) < report['total'] else None,
        'items': [serialize(review, evidence, reveal=True) for review, evidence in rows]}


@router.get('/{symbol}', response_model=SentimentOut)
async def get_sentiment(symbol: str, provider: str | None = Query(None),
    user=Depends(get_current_user), redis=Depends(get_redis), db=Depends(get_db)):
    symbol = normalize_symbol(symbol)
    settings = get_settings()
    provider = provider or settings.sentiment_news_provider
    instance = get_sentiment_provider(provider)
    async def report_health(sources):
        try:
            await redis.set(f'sentiment:health:rss:{symbol}', json.dumps(sources, default=lambda value: value.isoformat()), ex=86400)
        except RedisError:
            pass
    if provider.lower() == 'rss':
        instance.health_reporter = report_health
    settings = get_settings()
    # Credential fingerprint invalidates cached evidence when operator changes providers' keys.
    fingerprint = hashlib.sha256(f'{settings.newsapi_api_key}:{settings.hf_token}'.encode()).hexdigest()[:16]
    key = f'sentiment:v4:{POLICY}:{provider}:{symbol}:{settings.sentiment_inference_mode}:{REVISION}:{settings.newsapi_delay_hours}:{settings.rss_news_window_hours}:{fingerprint}'
    async with _locks[symbol]:
        try:
            cached = await redis.get(key)
            if cached:
                result = SentimentOut.model_validate_json(cached).model_copy(update={'cached': True})
                if result.provider == 'rss' and result.aggregation.get('method') == POLICY:
                    result.aggregation = aggregate_news([item.model_dump() for item in result.articles],
                        datetime.now(timezone.utc), result.aggregation.get('deduplicated_headlines', 0))
                    fresh = result.aggregation['fresh']
                    result.score, result.label, result.confidence = fresh['score'], fresh['label'], fresh['confidence']
                    result.counts, result.probabilities = fresh['counts'], fresh['probabilities']
                result.quality = check_sample(result)
                await capture(db, user.id, result)
                return result
        except (RedisError, ValueError):
            pass
        try:
            async with asyncio.timeout(45):
                result = SentimentOut.model_validate(asdict(await instance.get_sentiment(symbol)))
        except TimeoutError:
            raise AppError('SENTIMENT_TIMEOUT', 'News sentiment timed out. Retry later.', 503) from None
        result.quality = check_sample(result)
        await capture(db, user.id, result)
        try:
            await redis.set(key, result.model_dump_json(), ex=300)
        except RedisError:
            pass
        return result
