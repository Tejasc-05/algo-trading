from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import httpx
import pytest
from xml.etree.ElementTree import ParseError
from app.core.exceptions import AppError
from app.sentiment.rss import RSSSentimentProvider, parse_feed, MAX_BYTES
from app.core.config import get_settings

pytestmark = pytest.mark.asyncio


def feed(title='Bitcoin gains', hours=1, url='https://example.com/news'):
    stamp = format_datetime(datetime.now(timezone.utc)-timedelta(hours=hours))
    return f'<rss><channel><item><title>{title}</title><link>{url}</link><pubDate>{stamp}</pubDate></item></channel></rss>'.encode()


async def test_rss_no_key_partial_coverage_and_cache(client, auth_headers, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings,'sentiment_news_provider','rss')
    monkeypatch.setattr(settings,'sentiment_inference_mode','local')
    monkeypatch.setattr(settings,'hf_token',None)
    monkeypatch.setattr(settings,'newsapi_api_key',None)
    original=httpx.AsyncClient
    seen=[]
    def handler(request):
        seen.append(request)
        assert 'Authorization' not in request.headers and 'auth_token' not in request.url.params
        if request.url.host == 'cointelegraph.com': return httpx.Response(200,content=feed())
        return httpx.Response(503)
    monkeypatch.setattr('httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(handler),**kwargs))
    async def score(self,texts): return [{'positive':.8,'neutral':.1,'negative':.1} for _ in texts]
    monkeypatch.setattr('app.sentiment.local_model.LocalFinBERTScorer.score',score)
    response=await client.get('/api/sentiment/BTC?provider=rss',headers=auth_headers)
    assert response.status_code==200,response.text
    data=response.json()
    assert data['provider']=='rss' and data['feed_delay_hours']==0
    assert data['warnings']==['CoinDesk feed unavailable']
    assert data['articles'][0]['source']=='Cointelegraph'
    assert (await client.get('/api/sentiment/BTC?provider=rss',headers=auth_headers)).json()['cached']
    assert len(seen)==2
    health = (await client.get('/api/sentiment/health/BTC',headers=auth_headers)).json()['sources']
    assert health[0]['status']=='reachable' and health[0]['matching_headlines']==1
    assert health[1]['status']=='unavailable'
    reviews = (await client.get('/api/sentiment/reviews/BTC',headers=auth_headers)).json()
    assert reviews['metrics']['total']==1 and 'label' not in reviews['items'][0]['article']


@pytest.mark.parametrize('data',[b'<!DOCTYPE rss [<!ENTITY a "boom">]><rss/>', b'bad XML', b'x'*(MAX_BYTES+1)])
async def test_unsafe_or_invalid_xml_rejected(data):
    with pytest.raises((ValueError, ParseError)): parse_feed(data,'Test','BTC',datetime.now(timezone.utc))


async def test_asset_freshness_and_url_filters():
    now=datetime.now(timezone.utc)
    assert parse_feed(feed('Ethereum gains'),'Test','BTC',now)==[]
    assert parse_feed(feed(hours=25),'Test','BTC',now)==[]
    assert parse_feed(feed(hours=-1),'Test','BTC',now)==[]
    assert parse_feed(feed(url='javascript:alert(1)'),'Test','BTC',now)==[]
    assert len(parse_feed(feed('Ethereum gains'),'Test','ETH',now))==1


async def test_no_matching_headlines_not_neutral(monkeypatch):
    original=httpx.AsyncClient
    monkeypatch.setattr('httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=feed('Other crypto news'))),**kwargs))
    with pytest.raises(AppError) as exc: await RSSSentimentProvider().get_sentiment('BTC')
    assert exc.value.code=='SENTIMENT_NO_RECENT_NEWS'


async def test_health_survives_total_feed_failure(client, auth_headers, monkeypatch):
    monkeypatch.setattr(get_settings(),'sentiment_news_provider','rss')
    original=httpx.AsyncClient
    monkeypatch.setattr('httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(lambda request:httpx.Response(503)),**kwargs))
    assert (await client.get('/api/sentiment/BTC',headers=auth_headers)).status_code==503
    health = (await client.get('/api/sentiment/health/BTC',headers=auth_headers)).json()['sources']
    assert all(source['status']=='unavailable' and source['checked_at'] for source in health)
    assert (await client.get('/api/sentiment/reviews/BTC',headers=auth_headers)).json()['metrics']['total']==0
