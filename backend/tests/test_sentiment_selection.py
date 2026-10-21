"""News diversity, conservative deduplication, freshness and weighting behavior."""
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import httpx
import pytest
from app.sentiment.news_selection import select_stories, aggregate_news
from app.sentiment.rss import FEEDS, RSSSentimentProvider
from app.schemas.sentiment import SentimentOut
from app.sentiment.quality import check_sample
from app.core.config import get_settings

NOW = datetime(2026,10,13,12,tzinfo=timezone.utc)
POS = {'positive':.9,'negative':.1,'neutral':0}
NEG = {'positive':.1,'negative':.9,'neutral':0}


def article(title, source='Cointelegraph', age=1, probs=POS, url=None):
    host={'Cointelegraph':'cointelegraph.com','CoinDesk':'coindesk.com','Decrypt':'decrypt.co'}[source]
    return dict(id=title, title=title, source=source, summary='',url=url or f'https://{host}/news/{title.replace(" ","-")}',
        published_at=NOW-timedelta(hours=age), probabilities=probs, label=max(probs,key=probs.get),
        score=probs['positive']-probs['negative'], confidence=max(probs.values()))


def test_freshness_weighting_and_older_context_exclusion():
    result=aggregate_news([article('Bitcoin recent positive',age=1),
        article('Bitcoin recent negative',source='CoinDesk',age=13,probs=NEG),
        article('Bitcoin historical negative',age=30,probs=NEG)],NOW,0)
    assert result['fresh']['score']==pytest.approx(.8/3)
    assert result['fresh']['publisher_count']==2
    assert result['older']['score']==pytest.approx(-.8)
    assert result['older']['headline_count']==1


def test_older_only_has_no_current_score_or_fabricated_neutral_label():
    result=aggregate_news([article('Bitcoin historic news',age=30)],NOW,0)
    assert result['fresh']['score'] is None and result['fresh']['label'] is None
    assert result['fresh']['confidence'] is None and result['fresh']['probabilities']=={}
    assert result['older']['label']=='positive'


def test_same_story_cross_publisher_counts_once_and_retains_provenance():
    stories,removed=select_stories([
        article('Bitcoin ETF inflows surge as institutional demand reaches record levels', age=2),
        article('BTC ETF inflows surge as institutional demand reaches record levels today',source='Decrypt',age=1),
        article('Ethereum upgrade delayed after developers report consensus bug',source='CoinDesk')])
    assert removed==1 and len(stories)==2
    representative=next(s for s in stories if s['source']=='Decrypt')
    assert representative['related_sources']==['Cointelegraph','Decrypt']
    assert aggregate_news(stories,NOW,removed)['fresh']['headline_count']==2


@pytest.mark.parametrize('other',[
    'Bitcoin ETF inflows reach 200 million as institutional demand rises today',
    'Bitcoin ETF inflows reach 100 million as institutional demand falls today',
    'Bitcoin ETF inflows do not reach 100 million as institutional demand rises today'])
def test_different_numbers_and_opposing_language_do_not_merge(other):
    stories,removed=select_stories([article('Bitcoin ETF inflows reach 100 million as institutional demand rises today'),
        article(other,source='CoinDesk')])
    assert len(stories)==2 and removed==0


def test_tracking_urls_and_title_punctuation_deduplicate():
    stories,removed=select_stories([article('Bitcoin news',url='https://cointelegraph.com/news/one?utm_source=rss#section'),
        article('BITCOIN NEWS!!!',age=2,url='https://cointelegraph.com/news/one')])
    assert len(stories)==1 and removed==1


def test_older_publisher_does_not_make_fresh_coverage_diverse():
    rows=[article(f'Bitcoin story {n}') for n in range(3)]+[article('Bitcoin old publisher',source='Decrypt',age=30)]
    aggregation=aggregate_news(rows,NOW,0)
    result=SentimentOut(symbol='BTC',score=.8,label='positive',confidence=.9,provider='rss',model='test',as_of=NOW,
        articles=rows,probabilities=POS,counts={},aggregation=aggregation)
    report=check_sample(result,NOW)
    assert report['publisher_count']==2 and report['fresh_publisher_count']==1
    assert next(c for c in report['checks'] if c['key']=='coverage')['status']=='attention'
    assert next(c for c in report['checks'] if c['key']=='freshness')['status']=='pass'
    assert next(c for c in report['checks'] if c['key']=='publisher_links')['status']=='pass'


@pytest.mark.asyncio
async def test_three_public_sources_correct_urls_and_old_only_response(client,auth_headers,monkeypatch):
    monkeypatch.setattr(get_settings(),'sentiment_news_provider','rss')
    monkeypatch.setattr(get_settings(),'sentiment_inference_mode','local')
    monkeypatch.setattr(get_settings(),'rss_news_window_hours',72)
    original=httpx.AsyncClient
    requests=[]
    def handler(request):
        requests.append(request)
        assert 'authorization' not in request.headers
        assert request.url.path != '/arc/outboundfeeds/rss/'
        if request.url.host=='decrypt.co': assert request.url.path=='/feed'
        host=request.url.host
        title=f'Bitcoin earlier update from {host}'
        stamp=format_datetime(datetime.now(timezone.utc)-timedelta(hours=30))
        body=f'<rss><channel><item><title>{title}</title><link>https://{host}/news/one</link><pubDate>{stamp}</pubDate></item></channel></rss>'
        return httpx.Response(200,content=body.encode())
    monkeypatch.setattr('httpx.AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    async def score(self,texts): return [POS for _ in texts]
    monkeypatch.setattr('app.sentiment.local_model.LocalFinBERTScorer.score',score)
    response=await client.get('/api/sentiment/BTC',headers=auth_headers)
    assert response.status_code==200,response.text
    data=response.json()
    assert data['score'] is None and data['label'] is None and data['confidence'] is None
    assert data['aggregation']['older']['headline_count']==3
    assert any('No headlines within 24 hours' in w for w in data['warnings'])
    assert len(requests)==3 and {r.url.host for r in requests}=={'cointelegraph.com','www.coindesk.com','decrypt.co'}
    health=(await client.get('/api/sentiment/health/BTC',headers=auth_headers)).json()['sources']
    assert len(health)==3 and all(s['status']=='reachable' for s in health)
    assert FEEDS['CoinDesk'].endswith('/rss')

@pytest.mark.asyncio
async def test_cached_headline_crossing_24_hours_stops_influencing_recent_score(client,auth_headers,monkeypatch):
    from app.sentiment.service import SentimentResult
    import app.api.routes.sentiment as routes
    clock=[NOW]
    class Clock:
        @staticmethod
        def now(tz=None): return clock[0]
    monkeypatch.setattr(routes,'datetime',Clock)
    row=article('Bitcoin just under the freshness limit',age=24-1/60)
    group=aggregate_news([row],NOW,0)
    calls=[]
    class Provider:
        async def get_sentiment(self,symbol):
            calls.append(symbol)
            return SentimentResult(symbol='BTC',score=.8,label='positive',confidence=.9,
                as_of=NOW,provider='rss',model='test',articles=[row],counts={'positive':1,'negative':0,'neutral':0},
                probabilities=POS,aggregation=group)
    monkeypatch.setattr(routes,'get_sentiment_provider',lambda name:Provider())
    first=await client.get('/api/sentiment/BTC?provider=rss',headers=auth_headers)
    assert first.status_code==200 and first.json()['score']==pytest.approx(.8)
    clock[0]=NOW+timedelta(minutes=2)
    cached=await client.get('/api/sentiment/BTC?provider=rss',headers=auth_headers)
    data=cached.json()
    assert data['cached'] and data['score'] is None and data['label'] is None
    assert data['aggregation']['fresh']['headline_count']==0 and data['aggregation']['older']['headline_count']==1
    assert data['aggregation']['reference_at']==clock[0].isoformat()
    assert calls==['BTC']
