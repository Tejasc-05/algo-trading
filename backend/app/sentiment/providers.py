"""Real news collection separated from model inference."""
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.sentiment.service import SentimentProvider, SentimentResult
from app.sentiment.scoring import FinBERTScorer, MODEL
from app.sentiment.local_model import LocalFinBERTScorer, REVISION

SYMBOLS = {'BTC': 'Bitcoin', 'ETH': 'Ethereum'}


def normalize_symbol(value):
    symbol = value.strip().upper()
    if symbol not in SYMBOLS:
        raise AppError('SENTIMENT_SYMBOL_UNSUPPORTED', 'Choose BTC or ETH for news sentiment.', 422)
    return symbol


class UnavailableSentimentProvider(SentimentProvider):
    def __init__(self, api_key=None):
        pass

    async def get_sentiment(self, symbol):
        raise AppError('SENTIMENT_UNAVAILABLE', 'This news provider is not integrated yet. Select NewsAPI.', 503)


class NewsAPISentimentProvider(SentimentProvider):
    def __init__(self, api_key=None):
        settings = get_settings()
        self.api_key = api_key or settings.newsapi_api_key
        self.mode = settings.sentiment_inference_mode
        self.scorer = LocalFinBERTScorer() if self.mode == 'local' else FinBERTScorer(settings.hf_token)
        self.delay_hours = settings.newsapi_delay_hours

    async def get_sentiment(self, symbol):
        symbol = normalize_symbol(symbol)
        if not self.api_key or (self.mode == 'hosted' and not self.scorer.token):
            message = 'News sentiment needs backend NEWSAPI_API_KEY configuration.' if self.mode == 'local' else 'News sentiment needs backend NEWSAPI_API_KEY and HF_TOKEN configuration.'
            raise AppError('SENTIMENT_UNAVAILABLE', message, 503)
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=self.delay_hours)
        oldest = cutoff - timedelta(hours=24)
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
                response = await client.get('https://newsapi.org/v2/everything',
                    headers={'X-Api-Key': self.api_key}, params={'q': SYMBOLS[symbol], 'searchIn': 'title',
                    'language': 'en', 'from': oldest.isoformat(), 'to': cutoff.isoformat(),
                    'sortBy': 'publishedAt', 'pageSize': 20})
                response.raise_for_status()
                payload = response.json()
                if payload.get('status') != 'ok' or not isinstance(payload.get('articles'), list):
                    raise ValueError('Invalid news response')
        except (httpx.HTTPError, ValueError, AttributeError):
            raise AppError('SENTIMENT_NEWS_UNAVAILABLE', 'NewsAPI request failed. Check the backend key, news plan and quota.', 503) from None
        articles = []
        seen = set()
        for raw in payload['articles']:
            try:
                title = str(raw.get('title') or '').strip()
                url = str(raw.get('url') or '')
                parsed = urlparse(url)
                stamp = datetime.fromisoformat(raw['publishedAt'].replace('Z', '+00:00'))
                signature = title.casefold()
                if not title or title == '[Removed]' or signature in seen or parsed.scheme not in {'https', 'http'} or not parsed.hostname or parsed.username or parsed.password:
                    continue
                if stamp.tzinfo is None or not oldest <= stamp <= cutoff:
                    continue
                seen.add(signature)
                articles.append({'id': hashlib.sha256(url.encode()).hexdigest()[:20], 'title': title[:1000],
                    'url': url, 'source': str((raw.get('source') or {}).get('name') or parsed.hostname)[:150],
                    'published_at': stamp, 'summary': str(raw.get('description') or '')[:300]})
            except (ValueError, TypeError, KeyError, AttributeError):
                continue
        articles = articles[:10]
        if not articles:
            raise AppError('SENTIMENT_NO_RECENT_NEWS', 'No usable headlines found in the configured 24-hour news window. No sentiment score was generated.', 503)
        scored = await self.scorer.score([item['title'] for item in articles])
        aggregate = {label: sum(item[label] for item in scored) / len(scored) for label in ('positive', 'negative', 'neutral')}
        label = max(aggregate, key=aggregate.get)
        counts = dict.fromkeys(aggregate, 0)
        for article, values in zip(articles, scored, strict=True):
            article_label = max(values, key=values.get)
            counts[article_label] += 1
            article.update(label=article_label, score=values['positive'] - values['negative'], confidence=values[article_label], probabilities=values)
        return SentimentResult(symbol=symbol, score=aggregate['positive'] - aggregate['negative'], label=label,
            confidence=aggregate[label], as_of=now, provider='newsapi', model=MODEL, model_revision=REVISION if self.mode == 'local' else 'hosted-unpinned',
            articles=articles, counts=counts, probabilities=aggregate, feed_delay_hours=self.delay_hours, inference_mode=self.mode)


PROVIDER_REGISTRY = {'newsapi': NewsAPISentimentProvider,
    'cryptopanic': UnavailableSentimentProvider, 'twitter': UnavailableSentimentProvider}


def get_sentiment_provider(provider_name, api_key=None):
    if provider_name.lower() == 'rss':
        from app.sentiment.rss import RSSSentimentProvider
        return RSSSentimentProvider()
    cls = PROVIDER_REGISTRY.get(provider_name.lower())
    if cls is None:
        raise AppError('UNKNOWN_PROVIDER', 'Unknown sentiment provider', 400)
    return cls(api_key=api_key)
