"""Ownership, immutable observation, blind labeling, and metric arithmetic."""
from datetime import datetime, timezone
import pytest
from app.schemas.sentiment import SentimentOut
from app.sentiment.validation import capture
from app.database.models.sentiment import SentimentEvidence
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


def evidence():
    now = datetime.now(timezone.utc)
    articles = []
    for index, label in enumerate(('positive', 'negative', 'neutral')):
        articles.append(dict(id=str(index), title=f'Bitcoin headline {index}', summary='',
            source='Test', url=f'https://example.com/{index}', published_at=now,
            label=label, score=0, confidence=.8, probabilities={label:.8}))
    return SentimentOut(symbol='BTC', score=0, label='neutral', confidence=.8,
        as_of=now, provider='rss', model='test', model_revision='test-v1', articles=articles,
        counts={}, probabilities={})


async def seed(client, headers, db):
    me = (await client.get('/api/auth/me', headers=headers)).json()
    await capture(db, me['id'], evidence())
    return (await client.get('/api/sentiment/reviews/BTC', headers=headers)).json()


async def test_review_authentication(client):
    for path in ('/api/sentiment/reviews/BTC', '/api/sentiment/export/BTC', '/api/sentiment/health/BTC'):
        assert (await client.get(path)).status_code == 401


async def test_repeat_ingestion_blind_reviews_and_ownership(client, auth_headers, db_session):
    first = await seed(client, auth_headers, db_session)
    stamps = {row.id: row.first_seen_at for row in (await db_session.scalars(select(SentimentEvidence))).all()}
    again = await seed(client, auth_headers, db_session)
    assert first['metrics']['total'] == again['metrics']['total'] == 3
    assert all('label' not in item['article'] and 'confidence' not in item['article'] for item in first['items'])
    assert {row.id: row.first_seen_at for row in (await db_session.scalars(select(SentimentEvidence))).all()} == stamps
    token = (await client.post('/api/auth/register', json={'email':'other@example.com','password':'password123'})).json()['access_token']
    other = {'Authorization':f'Bearer {token}'}
    assert (await client.get('/api/sentiment/export/BTC', headers=other)).json()['items'] == []
    item = first['items'][0]
    response = await client.put(f"/api/sentiment/reviews/item/{item['id']}", headers=other,
        json={'human_label':'negative', 'source_verdict':'verified'})
    assert response.status_code == 404
    saved = await client.put(f"/api/sentiment/reviews/item/{item['id']}", headers=auth_headers,
        json={'human_label':'negative','source_verdict':'verified','notes':'Checked original'})
    assert saved.status_code == 200 and 'label' in saved.json()['article']
    assert saved.json()['reviewed_at']
    assert (await client.get('/api/sentiment/reviews/ETH',headers=auth_headers)).json()['items'] == []


async def test_metrics_exclusions_and_export_pagination(client, auth_headers, db_session):
    await seed(client, auth_headers, db_session)
    exported = (await client.get('/api/sentiment/export/BTC',headers=auth_headers)).json()
    for item in exported['items']:
        predicted = item['article']['label']
        body = {'human_label':'ambiguous' if predicted == 'neutral' else 'positive', 'source_verdict':'verified'}
        assert (await client.put(f"/api/sentiment/reviews/item/{item['id']}",headers=auth_headers,json=body)).status_code==200
    report = (await client.get('/api/sentiment/reviews/BTC?limit=1',headers=auth_headers)).json()['metrics']
    assert (report['total'],report['reviewed'],report['evaluated'],report['excluded']) == (3,3,2,1)
    assert report['accuracy'] == .5
    assert report['per_class']['positive']['precision'] == 1
    assert report['per_class']['positive']['recall'] == .5
    assert report['macro_f1'] == pytest.approx(2/9)
    page = (await client.get('/api/sentiment/export/BTC?limit=1',headers=auth_headers)).json()
    assert len(page['items']) == 1 and page['next_offset'] == 1
    assert 'model_revision' in page['items'][0]['article']
    item = exported['items'][0]
    assert (await client.put(f"/api/sentiment/reviews/item/{item['id']}",headers=auth_headers,json={'human_label':'buy'})).status_code==422
    assert (await client.put(f"/api/sentiment/reviews/item/{item['id']}",headers=auth_headers,json={'notes':'x'*2001})).status_code==422
    assert (await client.get('/api/sentiment/reviews/DOGE',headers=auth_headers)).status_code==422
    await client.put(f"/api/sentiment/reviews/item/{item['id']}",headers=auth_headers,json={'human_label':None})
    pending = (await client.get('/api/sentiment/reviews/BTC',headers=auth_headers)).json()
    assert 'label' not in next(row for row in pending['items'] if row['id']==item['id'])['article']
