"""Allowlisted public publisher feeds. Titles only, no article scraping or keys."""
import asyncio
import hashlib
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.sentiment.providers import normalize_symbol
from app.sentiment.local_model import LocalFinBERTScorer, REVISION
from app.sentiment.scoring import FinBERTScorer, MODEL
from app.sentiment.service import SentimentProvider, SentimentResult
from app.sentiment.news_selection import select_stories, aggregate_news

FEEDS = {'Cointelegraph': 'https://cointelegraph.com/rss',
    'CoinDesk': 'https://www.coindesk.com/arc/outboundfeeds/rss',
    'Decrypt': 'https://decrypt.co/feed'}
MAX_BYTES = 500_000


def parse_feed(data, source, symbol, now, window_hours=24):
    # Accept UTF-8 only and reject DTD/entity declarations before XML parsing.
    # This prevents entity expansion without processing arbitrary publisher HTML.
    text = data.decode('utf-8-sig')
    if len(data) > MAX_BYTES or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():
        raise ValueError('Unsupported XML')
    root = ElementTree.fromstring(text)
    if root.tag != 'rss' or root.find('channel') is None:
        raise ValueError('Unsupported feed structure')
    matches = re.compile(r'\b(bitcoin|btc)\b' if symbol == 'BTC' else r'\b(ethereum|ether|eth)\b', re.I)
    articles = []
    for item in root.findall('./channel/item')[:100]:
        try:
            title = (item.findtext('title') or '').strip()
            url = (item.findtext('link') or '').strip()
            link = urlparse(url)
            stamp = parsedate_to_datetime(item.findtext('pubDate') or '')
            if not matches.search(title) or not title or link.scheme not in {'http','https'} or not link.hostname or link.username or link.password:
                continue
            if stamp.tzinfo is None or not now-timedelta(hours=window_hours) <= stamp <= now:
                continue
            articles.append({'id': hashlib.sha256(url.encode()).hexdigest()[:20], 'title':title[:1000],
                'url':url, 'source':source, 'published_at':stamp, 'summary':''})
        except (ValueError, TypeError, OverflowError):
            continue
    return articles


async def fetch_feed(client, source, url, symbol, now, window_hours):
    try:
        async with client.stream('GET', url) as response:
            response.raise_for_status()
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise ValueError('Feed too large')
        return parse_feed(bytes(data), source, symbol, now, window_hours), None
    except (httpx.HTTPError, ValueError, UnicodeError, ElementTree.ParseError):
        return [], f'{source} feed unavailable'


class RSSSentimentProvider(SentimentProvider):
    def __init__(self, api_key=None):
        settings = get_settings()
        self.mode = settings.sentiment_inference_mode
        self.health_reporter = None
        self.window_hours = settings.rss_news_window_hours
        self.scorer = LocalFinBERTScorer() if self.mode == 'local' else FinBERTScorer(settings.hf_token)

    async def get_sentiment(self, symbol):
        symbol = normalize_symbol(symbol)
        now = datetime.now(timezone.utc)
        async with httpx.AsyncClient(timeout=15, follow_redirects=False,
            headers={'User-Agent':'AlgoFlow/0.1 RSS reader'}) as client:
            results = await asyncio.gather(*(fetch_feed(client, name, url, symbol, now, self.window_hours) for name,url in FEEDS.items()))
        if self.health_reporter:
            await self.health_reporter([{'source': name, 'feed_url': url,
                'status': 'unavailable' if warning else 'reachable',
                'checked_at': now.isoformat(), 'matching_headlines': len(rows),
                'newest_published_at': max((item['published_at'] for item in rows), default=None),
                'window_hours': self.window_hours}
                for (name, url), (rows, warning) in zip(FEEDS.items(), results, strict=True)])
        warnings = [warning for _,warning in results if warning]
        if len(warnings) == len(FEEDS):
            raise AppError('SENTIMENT_NEWS_UNAVAILABLE', 'Publisher feeds are unavailable. Retry later.', 503)
        articles, removed = select_stories([item for rows,_ in results for item in rows])
        if not articles:
            raise AppError('SENTIMENT_NO_RECENT_NEWS', f'No matching headlines in the publisher feeds during the last {self.window_hours} hours. No score generated.', 503)
        scored = await self.scorer.score([item['title'] for item in articles])
        for item, values in zip(articles,scored,strict=True):
            label = max(values,key=values.get)
            item.update(label=label,score=values['positive']-values['negative'],confidence=values[label],probabilities=values)
        aggregation = aggregate_news(articles, now, removed)
        fresh = aggregation['fresh']
        if not fresh['headline_count']:
            warnings.append('No headlines within 24 hours; current sentiment is unavailable. Older news is context only.')
        elif fresh['headline_count'] < 3 or fresh['publisher_count'] < 2:
            warnings.append('Fresh coverage is limited: fewer than three distinct headlines or two publishers within 24 hours.')
        return SentimentResult(symbol=symbol,score=fresh['score'],label=fresh['label'],
            confidence=fresh['confidence'],as_of=now,provider='rss',model=MODEL, model_revision=REVISION if self.mode == 'local' else 'hosted-unpinned',articles=articles,counts=fresh['counts'],
            probabilities=fresh['probabilities'],aggregation=aggregation,feed_delay_hours=0,inference_mode=self.mode,warnings=warnings,window_hours=self.window_hours)
