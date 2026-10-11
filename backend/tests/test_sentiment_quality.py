"""Automated checks detect quality failures without fabricating validation labels."""
from datetime import datetime, timedelta, timezone
import pytest
from app.schemas.sentiment import SentimentOut
from app.sentiment.quality import check_sample

NOW = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)


def sample():
    articles = []
    for index in range(3):
        source = 'CoinDesk' if index == 1 else 'Cointelegraph'
        host = 'coindesk.com' if index == 1 else 'cointelegraph.com'
        articles.append(dict(id=str(index), title=f'Bitcoin announcement {index}', summary='', source=source,
            url=f'https://{host}/news/{index}', published_at=NOW-timedelta(hours=1), label='positive',
            score=.7, confidence=.8, probabilities={'positive':.8,'negative':.1,'neutral':.1}))
    return SentimentOut(symbol='BTC', score=.7, label='positive', confidence=.8, as_of=NOW,
        provider='rss', model='test', articles=articles, counts={}, probabilities={})


def test_fresh_diverse_sample_passes_without_accuracy_claim():
    result = sample()
    report = check_sample(result, NOW)
    assert report['status']=='checks_passed'
    assert report['fresh_headlines']==3 and report['publisher_count']==2
    assert report['model_accuracy']=='not_measured' and not report['trading_integration_enabled']
    assert not report['flagged_headlines']


def test_duplicate_tracking_links_and_title_normalization():
    result = sample()
    result.articles[2].title = 'BITCOIN announcement 0!!!'
    result.articles[2].url = result.articles[0].url+'?utm_source=rss#fragment'
    report = check_sample(result, NOW)
    duplicate = next(row for row in report['checks'] if row['key']=='duplicates')
    assert duplicate['status']=='attention'
    assert {row['id'] for row in report['flagged_headlines']} == {'0','2'}


def test_uncertainty_and_bad_scores():
    result = sample()
    item = result.articles[0]
    item.probabilities = {'positive':.45, 'negative':.35, 'neutral':.2}
    item.confidence = .45; item.score = .1
    result.articles[1].probabilities = {'positive':float('nan'), 'negative':.1, 'neutral':.1}
    result.articles[2].score = -.7
    report = check_sample(result, NOW)
    checks = {row['key']:row['status'] for row in report['checks']}
    assert checks['uncertainty']==checks['probabilities']=='attention'
    assert len(report['flagged_headlines'])==3


def test_stale_future_irrelevant_and_wrong_publisher():
    result = sample()
    result.articles[0].published_at = NOW-timedelta(hours=25)
    result.articles[1].published_at = NOW+timedelta(minutes=1)
    result.articles[2].title = 'Other assets rally'
    result.articles[2].url = 'https://cointelegraph.com.attacker.example/article'
    result.as_of = NOW-timedelta(minutes=11)
    result.warnings = ['CoinDesk feed unavailable']
    report = check_sample(result, NOW)
    checks = {row['key']:row['status'] for row in report['checks']}
    assert all(checks[key]=='attention' for key in ('freshness','asset_relevance','publisher_links','coverage','sample_age','feed_warnings'))
    assert report['fresh_headlines']==1


def test_diagnostics_recompute_freshness_on_cached_sample():
    result = sample()
    assert check_sample(result, NOW)['status']=='checks_passed'
    later = check_sample(result, NOW+timedelta(hours=25))
    assert later['status']=='attention' and later['fresh_headlines']==0
    assert result.articles[0].label=='positive'  # diagnostics never relabel evidence


@pytest.mark.asyncio
async def test_authenticated_read_automatically_checks_cache(client, auth_headers, monkeypatch, db_session):
    from app.sentiment.service import SentimentResult
    from app.database.models.sentiment import SentimentReview
    from sqlalchemy import select
    calls=[]
    result = sample().model_copy(update={'as_of':datetime.now(timezone.utc)})
    class Provider:
        async def get_sentiment(self, symbol):
            calls.append(symbol)
            return SentimentResult(**{key:value for key,value in result.model_dump().items() if key not in ('cached','quality')})
    monkeypatch.setattr('app.api.routes.sentiment.get_sentiment_provider',lambda name:Provider())
    first = await client.get('/api/sentiment/BTC',headers=auth_headers)
    assert first.status_code==200,first.text
    report=first.json()['quality']
    assert report['model_accuracy']=='not_measured' and report['checks']
    second = await client.get('/api/sentiment/BTC',headers=auth_headers)
    assert second.json()['cached'] and len(calls)==1
    reviews = (await db_session.scalars(select(SentimentReview))).all()
    assert len(reviews)==3
    assert all(row.human_label is None and row.source_verdict=='unverified' for row in reviews)
